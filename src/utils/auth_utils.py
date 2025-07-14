# src/services/auth_utils.py
from flask import current_app, session
from datetime import datetime
from src.models import db, User


def get_non_reserved_scopes():
    # Only filter 'openid' and 'profile' to keep 'offline_access' for refresh tokens
    reserved = {"openid", "profile","offline_access"}
    scopes = current_app.config["SCOPE"].split()

    # Logging to verify contents
    current_app.logger.debug("🔍 All configured scopes: %r", scopes)
    filtered = [s for s in scopes if s not in reserved]
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

def refresh_token_if_needed(user):
    """Check if user token needs refresh and refresh if necessary"""
    from src.services.microsoft_graph import MicrosoftGraphService
    
    if user.token_expired:
        current_app.logger.info(f"🔄 Token expired for user {user.id}, refreshing...")
        
        graph_service = MicrosoftGraphService(
            access_token=user.access_token,
            refresh_token=user.refresh_token,
            token_expires=user.token_expires,
            user_id=user.id
        )
        
        # This will automatically refresh the token and save it
        graph_service.ensure_valid_token()
        
        # Reload user from database to get updated tokens
        db.session.refresh(user)
    
    return user
