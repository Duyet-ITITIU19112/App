# src/services/auth_utils.py
from flask import current_app

def get_non_reserved_scopes():
    reserved = {"openid", "profile", "offline_access"}
    scopes = current_app.config["SCOPE"].split()
    # Logging to verify contents
    current_app.logger.debug("🔍 All configured scopes: %r", scopes)
    filtered = [s for s in scopes if s not in reserved]
    current_app.logger.debug("✅ Filtered non-reserved scopes: %r", filtered)
    return filtered
