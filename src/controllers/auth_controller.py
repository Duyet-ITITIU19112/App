# src/controllers/auth_controller.py
import requests
from msal import ConfidentialClientApplication
from flask import current_app
from datetime import datetime
import time

from msal.authority import Authority

from src.models.user_model import User
from src.models import db
from src.services.microsoft_graph import MicrosoftGraphService, OneDriveServiceError

def get_msal_app():
    authority = f"https://login.microsoftonline.com/{current_app.config['MS_TENANT_ID']}"
    try:
        # this will do the OIDC discovery under the hood
        return ConfidentialClientApplication(
            client_id=current_app.config["CLIENT_ID"],
            client_credential=current_app.config["CLIENT_SECRET"],
            authority=authority,
            validate_authority= False
        )
    except (requests.exceptions.ConnectionError, Authority.UnknownAuthority):
        current_app.logger.warning("⚠️ MSAL authority discovery failed—running in offline mode")
        # Return a dummy app with no-ops for get_authorization_request_url / acquire_token...
        class DummyApp:
            def get_authorization_request_url(self, *args, **kwargs):
                return "/"
            def acquire_token_by_authorization_code(self, *args, **kwargs):
                return {}
        return DummyApp()

def exchange_code_for_token(code: str) -> dict:
    ms_app = get_msal_app()
    scopes = [s for s in current_app.config["SCOPE"].split()
              if s not in {"openid", "profile", "offline_access"}]

    return ms_app.acquire_token_by_authorization_code(
        code,
        scopes=scopes,
        redirect_uri=current_app.config["REDIRECT_URI"]
    )

def get_user_profile(token_result: dict) -> dict:
    svc = MicrosoftGraphService(
        access_token=token_result["access_token"],
        refresh_token=token_result.get("refresh_token"),
        token_expires=time.time() + int(token_result.get("expires_in", 3600)),
        suppress_missing_user_id_warning=True
    )
    return svc.get_user_info()

def get_or_create_user(profile: dict, token_result: dict) -> User:
    ms_id = token_result.get("id_token_claims", {}).get("oid") or profile["id"]
    user = User.query.filter_by(ms_id=ms_id).first()

    expires_at = datetime.utcfromtimestamp(time.time() + int(token_result.get("expires_in", 3600)))

    if not user:
        user = User(
            ms_id=ms_id,
            name=profile.get("displayName"),
            email=profile.get("userPrincipalName", "").strip(),
            access_token=token_result["access_token"],
            refresh_token=token_result.get("refresh_token"),
            token_expires=expires_at
        )
        db.session.add(user)
        current_app.logger.info(f"👋 Created new user: {user.email}")
    else:
        user.access_token = token_result["access_token"]
        user.refresh_token = token_result.get("refresh_token")
        user.token_expires = expires_at
        current_app.logger.debug(f"🔁 Updated tokens for user: {user.email}")

    db.session.commit()
    return user

def refresh_token_if_needed(user: User) -> User:
    svc = MicrosoftGraphService(
        access_token=user.access_token,
        refresh_token=user.refresh_token,
        token_expires=user.token_expires,
        user_id=user.id
    )
    svc.ensure_valid_token()

    user.access_token = svc.access_token
    user.refresh_token = svc.refresh_token
    user.token_expires = datetime.utcfromtimestamp(svc.token_expires)
    db.session.commit()
    return user
