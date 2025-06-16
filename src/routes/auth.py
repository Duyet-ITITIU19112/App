import time
from flask import Blueprint, session, redirect, request, url_for, current_app
from msal import ConfidentialClientApplication
import uuid
from datetime import datetime, timedelta
from src.models.user_model import User
from src.models import db
from src.controllers.ingest_controller import ingest_user_onedrive_files
from src.services.microsoft_graph import MicrosoftGraphService, OneDriveServiceError
from src.services.auth_utils import get_non_reserved_scopes
from dotenv import load_dotenv

load_dotenv()

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))

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
    if not scopes:
        current_app.logger.warning("⚠️ No scopes defined for Microsoft OAuth.")
        return "No scopes configured", 500

    current_app.logger.debug("🔐 [LOGIN] Filtered scopes: %r", scopes)

    try:
        auth_url = ms_app.get_authorization_request_url(
            scopes=scopes,
            redirect_uri=current_app.config["REDIRECT_URI"],
            state=state
        )
        current_app.logger.debug("🌐 [LOGIN] Redirecting to: %s", auth_url)
        current_app.logger.debug("📦 [LOGIN] Session state saved: %s", state)
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
        current_app.logger.debug("🎟️ Token result: %r", result)
    except Exception as e:
        current_app.logger.exception("❌ MSAL token acquisition failed")
        return "Authentication failed.", 500

    if "access_token" not in result:
        current_app.logger.error("⚠️ Missing access_token in result: %r", result)
        return f"Auth failed: {result.get('error_description')}", 400

    # Calculate token expiry using consistent float time
    now = time.time()
    expires_in = int(result.get("expires_in", 3600))
    token_expires = now + expires_in
    expires_at = datetime.utcfromtimestamp(token_expires)

    # TEMPORARY svc just to fetch profile — no user_id yet
    svc_temp = MicrosoftGraphService(
        access_token=result["access_token"],
        refresh_token=result.get("refresh_token"),
        token_expires=token_expires
    )

    try:
        profile = svc_temp.get_user_info()
        current_app.logger.debug("👤 Retrieved profile: %r", profile)
    except OneDriveServiceError as e:
        current_app.logger.error("❌ Profile fetch failed: %s", e)
        return f"Failed to fetch profile: {e}", 500

    # ✅ Now create or update the user
    user = User.query.filter_by(ms_id=profile["id"]).first()
    if not user:
        user = User(
            ms_id=profile["id"],
            name=profile.get("displayName"),
            email=profile.get("userPrincipalName", "").strip(),
            access_token=result["access_token"],
            refresh_token=result.get("refresh_token"),
            token_expires=expires_at
        )
        db.session.add(user)
        current_app.logger.info("👋 New user created: %s", profile.get("displayName"))
    else:
        user.access_token = result["access_token"]
        user.refresh_token = result.get("refresh_token")
        user.token_expires = expires_at
        current_app.logger.debug("🔁 Existing user token updated: %s", profile.get("userPrincipalName"))

    db.session.commit()

    # ✅ Store session — login complete
    session["user_id"] = user.id

    # ✅ Final svc instance with user_id
    svc = MicrosoftGraphService(
        access_token=user.access_token,
        refresh_token=user.refresh_token,
        token_expires=token_expires,
        user_id=user.id
    )

    # ✅ Ensure token is usable and save it if refreshed
    svc.ensure_valid_token()
    user.access_token = svc.access_token
    user.refresh_token = svc.refresh_token
    user.token_expires = datetime.utcfromtimestamp(svc.token_expires)
    db.session.commit()

    # ✅ Now ingestion is safe — user is fully logged in
    try:
        ingest_user_onedrive_files(user, svc)
    except OneDriveServiceError as e:
        current_app.logger.error("⚠️ Ingestion error: %s", e)

    return redirect(url_for("files.browse"))

