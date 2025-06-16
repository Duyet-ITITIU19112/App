# src/services/auth_utils.py
from flask import current_app, session
from datetime import datetime
from src.models import db, User


RESERVED_SCOPES = {"openid", "profile", "offline_access"}  # <-- make sure this includes offline_access

def get_non_reserved_scopes():
    scope_string = current_app.config.get("SCOPE", "")
    scopes = scope_string.split()

    current_app.logger.debug("🔍 All configured scopes: %r", scopes)

    filtered = [s for s in scopes if s not in RESERVED_SCOPES]
    current_app.logger.debug("✅ Filtered non-reserved scopes: %r", filtered)

    return filtered
def save_updated_token(user_id, token_data):
    user = User.query.get(user_id)
    if not user:
        raise ValueError(f"User with ID {user_id} not found")

    user.access_token = token_data["access_token"]
    user.refresh_token = token_data["refresh_token"]
    user.token_expires = datetime.utcfromtimestamp(token_data["expires_at"])
    db.session.commit()
