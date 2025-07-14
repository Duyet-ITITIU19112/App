# src/routes/auth.py

import uuid
from datetime import datetime, timedelta

from flask import Blueprint, request, session, redirect, url_for, current_app
from flask_login import login_user, logout_user
from src.controllers.auth_controller import (
    get_msal_app,
    exchange_code_for_token,
    get_user_profile,
    get_or_create_user,
    refresh_token_if_needed
)
from src.models.subscription_model import Subscription
from src.services.microsoft_graph import MicrosoftGraphService
from src.utils.auth_utils import get_non_reserved_scopes
from src.models import db

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login")
def login():
    ms_app = get_msal_app()
    state = "int-" + uuid.uuid4().hex
    session["ms_state"] = state

    scopes = get_non_reserved_scopes()
    if not scopes:
        current_app.logger.warning("⚠️ No scopes defined for Microsoft OAuth.")
        return "No scopes configured", 500

    auth_url = ms_app.get_authorization_request_url(
        scopes=scopes,
        redirect_uri=current_app.config["REDIRECT_URI"],
        prompt="select_account",
        state=state
    )
    current_app.logger.debug("🌐 Redirecting to Microsoft Login: %s", auth_url)
    return redirect(auth_url)


@auth_bp.route("/callback")
def callback():
    incoming = request.args.get("state")
    expected = session.get("ms_state")
    if not incoming or incoming != expected:
        return "Invalid state", 400

    # ignore silent‐renew
    if not incoming.startswith("int-"):
        return "", 204

    # exchange code for tokens
    result = exchange_code_for_token(request.args["code"])
    if "access_token" not in result:
        return f"Authentication failed: {result.get('error_description')}", 400

    profile = get_user_profile(result)
    user = get_or_create_user(profile, result)

    # only clear delta_link for brand‐new users
    if user.delta_link is None:
        user.delta_link = None
        db.session.commit()

    # refresh tokens if needed
    user = refresh_token_if_needed(user)

    # log in
    login_user(user)
    session.pop("sync_started", None)

    # prepare Graph service
    svc = MicrosoftGraphService(
        access_token=user.access_token,
        refresh_token=user.refresh_token,
        token_expires=user.token_expires,
        user_id=user.id
    )

    # renew or create subscription
    sub = Subscription.query.filter_by(user_id=user.id).first()
    now = datetime.utcnow()
    if not sub or sub.expires_at <= now:
        # either no subscription yet, or it’s expired—(re)create
        expiration = now + timedelta(days=2)
        graph_sub = svc.create_subscription(
            change_type="created,updated",
            resource="/me/drive/root",
            notification_url=current_app.config["NOTIFICATIONS_URL"],
            client_state=str(user.id),
            expiration_datetime=expiration.isoformat() + "Z"
        )

        if not sub:
            sub = Subscription(
                sub_id=graph_sub["id"],
                user_id=user.id,
                client_state=str(user.id),
                expires_at=expiration
            )
            db.session.add(sub)
        else:
            sub.sub_id     = graph_sub["id"]
            sub.expires_at = expiration

        db.session.commit()
        current_app.logger.info(f"Subscribed to Graph notifications: {sub.sub_id} (expires {sub.expires_at})")

    return redirect(url_for("files.browse"))



@auth_bp.route("/logout")
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))
