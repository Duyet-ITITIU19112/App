import time
import requests
from flask import current_app
from msal import ConfidentialClientApplication

class OneDriveServiceError(Exception):
    """Raised when Graph API operations fail or token refresh errors occur."""
    pass

class MicrosoftGraphService:
    def __init__(self, access_token=None, refresh_token=None, token_expires=None):
        cfg = current_app.config
        authority = cfg["AUTHORITY"]

        self.app = ConfidentialClientApplication(
            client_id=cfg["CLIENT_ID"],
            client_credential=cfg["CLIENT_SECRET"],
            authority=authority
        )
        self.access_token = access_token
        self.refresh_token = refresh_token
        # token_expires can be a datetime.timestamp() or float since epoch
        self.token_expires = float(token_expires) if token_expires else 0
        self.headers = {}

    def _ensure_token(self):
        now = time.time()
        if not self.access_token or now >= self.token_expires:
            scopes_all = current_app.config["SCOPE"].split()
            # same filtering logic as before
            reserved = {"openid", "profile", "offline_access"}
            scopes = [s for s in scopes_all if s not in reserved]
            current_app.logger.debug("🔁 Refreshing token with scopes: %r", scopes)

            # Try silent first
            accounts = self.app.get_accounts()
            result = None
            if accounts:
                result = self.app.acquire_token_silent(scopes, account=accounts[0])

            # If that fails, use refresh_token
            if not result or "access_token" not in result:
                try:
                    result = self.app.acquire_token_by_refresh_token(
                        self.refresh_token,
                        scopes=scopes
                    )
                except ValueError as e:
                    current_app.logger.error("❌ Refresh token Msal ValueError: scopes=%r; error=%s", scopes, e)
                    raise OneDriveServiceError(f"Token refresh failed: {e}")

            if not result or "access_token" not in result:
                raise OneDriveServiceError(result.get("error_description", "Token refresh failed"))

            # Update tokens
            self.access_token = result["access_token"]
            self.refresh_token = result.get("refresh_token", self.refresh_token)
            self.token_expires = now + int(result["expires_in"])

        self.headers = {"Authorization": f"Bearer {self.access_token}"}

    def get_auth_url(self, state: str) -> str:
        return self.app.get_authorization_request_url(
            scopes=current_app.config["SCOPE"].split(),
            redirect_uri=current_app.config["REDIRECT_URI"],
            state=state
        )

    def acquire_token_by_code(self, code: str) -> dict:
        result = self.app.acquire_token_by_authorization_code(
            code,
            scopes=current_app.config["SCOPE"].split(),
            redirect_uri=current_app.config["REDIRECT_URI"]
        )
        if "access_token" not in result:
            raise OneDriveServiceError(result.get("error_description", "Auth failed"))

        now = time.time()
        self.access_token = result["access_token"]
        self.refresh_token = result.get("refresh_token")
        self.token_expires = now + int(result["expires_in"])
        return result

    def list_root_files(self) -> list:
        self._ensure_token()
        resp = requests.get(
            "https://graph.microsoft.com/v1.0/me/drive/root/children",
            headers=self.headers
        )
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return [
            item for item in resp.json().get("value", [])
            if "file" in item and item["name"].endswith((".txt", ".docx"))
        ]

    def fetch_file_content(self, file_id: str) -> bytes:
        self._ensure_token()
        resp = requests.get(
            f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}/content",
            headers=self.headers,
            stream=True
        )
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.content

    def get_user_info(self) -> dict:
        self._ensure_token()
        resp = requests.get(
            "https://graph.microsoft.com/v1.0/me",
            headers=self.headers
        )
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.json()
