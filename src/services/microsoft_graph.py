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
        return resp.json().get("value", [])


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
    def list_children(self, parent_id: str) -> list:
        self._ensure_token()
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{parent_id}/children"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        items = resp.json().get("value", [])
    # Optional sorting to list folders first:
        items.sort(key=lambda i: ("file" in i, i["name"].lower()))
        return items

    
    
    def get_item(self, item_id: str) -> dict:
        self._ensure_token()
        url = f"{self.BASE_URL}/me/drive/items/{item_id}"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.json()
    
    def get_embed_link(self, item_id: str) -> str:
        self._ensure_token()
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/preview"
        resp = requests.post(url, headers=self.headers)
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.json().get("previewLink")
    
    def get_embed_link(self, item_id):
        self._ensure_token()
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/preview"
        resp = requests.post(url, headers=self.headers, json={})
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.json().get("getUrl")

    def list_all_files_recursively(self, folder_id=None):
        self._ensure_token()
    
        base_url = "https://graph.microsoft.com/v1.0/me/drive"
        path = f"/items/{folder_id}/children" if folder_id else "/root/children"
        url = f"{base_url}{path}"
    
        all_files = []

        while url:
            resp = requests.get(url, headers=self.headers)
            if resp.status_code != 200:
                raise OneDriveServiceError(f"Graph error: {resp.text}")
            data = resp.json()

            for item in data.get("value", []):
                if "folder" in item:
                    try:
                        sub_items = self.list_all_files_recursively(item["id"])
                        all_files.extend(sub_items)
                    except OneDriveServiceError as e:
                        print(f"⚠️ Skipping folder '{item['name']}': {e}")
                elif "file" in item:
                    all_files.append(item)

            url = data.get("@odata.nextLink")  # pagination

        return all_files



