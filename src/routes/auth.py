from flask import Blueprint, session, redirect, request, url_for, current_app
from msal import ConfidentialClientApplication
import uuid
from datetime import datetime, timedelta

from src.models.user_model import User
from src.models import db
from src.controllers.ingest_controller import ingest_user_onedrive_files
from src.services.microsoft_graph import MicrosoftGraphService, OneDriveServiceError
from src.services.auth_utils import get_non_reserved_scopes

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login")
def login():
    ms_app = ConfidentialClientApplication(
        client_id=current_app.config["CLIENT_ID"],
        client_credential=current_app.config["CLIENT_SECRET"],
        authority=f"https://login.microsoftonline.com/{current_app.config['MS_TENANT_ID']}"
    )
    state = uuid.uuid4().hex
    session["ms_state"] = state

    scopes = get_non_reserved_scopes()
    current_app.logger.debug("🔐 [LOGIN] Filtered scopes: %r", scopes)

    try:
        auth_url = ms_app.get_authorization_request_url(
            scopes=scopes,
            redirect_uri=current_app.config["REDIRECT_URI"],
            state=state
        )
    except ValueError as e:
        current_app.logger.error("❌ MSAL login error: %s", e)
        return f"Internal error during login: {e}", 500

    return redirect(auth_url)


@auth_bp.route("/callback")
def callback():
    if request.args.get("state") != session.get("ms_state"):
        return "Invalid state", 400

    ms_app = ConfidentialClientApplication(
        client_id=current_app.config["CLIENT_ID"],
        client_credential=current_app.config["CLIENT_SECRET"],
        authority=f"https://login.microsoftonline.com/{current_app.config['MS_TENANT_ID']}"
    )

    scopes = get_non_reserved_scopes()
    current_app.logger.debug("🛠️ [CALLBACK] Filtered scopes: %r", scopes)

    try:
        result = ms_app.acquire_token_by_authorization_code(
            request.args["code"],
            scopes=scopes,
            redirect_uri=current_app.config["REDIRECT_URI"]
        )
    except ValueError as e:
        current_app.logger.error("❌ MSAL callback error: %s", e)
        return f"Authentication failed: {e}", 500

    if "access_token" not in result:
        current_app.logger.error("⚠️ Missing access_token in result: %r", result)
        return f"Auth failed: {result.get('error_description')}", 400

    expires_at = datetime.utcnow() + timedelta(seconds=int(result["expires_in"]))
    svc = MicrosoftGraphService(
        access_token=result["access_token"],
        refresh_token=result.get("refresh_token"),
        token_expires=expires_at.timestamp()
    )

    try:
        profile = svc.get_user_info()
    except OneDriveServiceError as e:
        current_app.logger.error("❌ Profile fetch failed: %s", e)
        return f"Failed to fetch profile: {e}", 500

    user = User.query.filter_by(ms_id=profile["id"]).first()
    if not user:
        user = User(
            ms_id=profile["id"],
            name=profile.get("displayName"),
            email=profile.get("userPrincipalName"),
            access_token=result["access_token"],
            refresh_token=result.get("refresh_token"),
            token_expires=expires_at
        )
        db.session.add(user)
    else:
        user.access_token = result["access_token"]
        user.refresh_token = result.get("refresh_token")
        user.token_expires = expires_at

    db.session.commit()
    session["user_id"] = user.id

    try:
        ingest_user_onedrive_files(user)
    except OneDriveServiceError as e:
        current_app.logger.error("⚠️ Ingestion error: %s", e)

    # ✅ Redirect to your main dashboard page
    return redirect(url_for("search.browse"))
