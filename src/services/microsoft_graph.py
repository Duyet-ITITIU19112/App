import time
import requests
from datetime import datetime
from msal import ConfidentialClientApplication
from flask import current_app
import requests
from src.utils.auth_utils import save_updated_token


class OneDriveServiceError(Exception):
    """Raised when Graph API operations fail or token refresh errors occur."""
    pass


class MicrosoftGraphService:
    BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(
            self,
            access_token=None,
            refresh_token=None,
            token_expires=None,
            user_id=None,
            suppress_missing_user_id_warning=False
    ):
        cfg = current_app.config
        self.app = ConfidentialClientApplication(
            client_id=cfg["CLIENT_ID"],
            client_credential=cfg["CLIENT_SECRET"],
            authority=cfg["AUTHORITY"]
        )
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.user_id = user_id
        if isinstance(token_expires, datetime):
            self.token_expires = token_expires.timestamp()
        else:
            self.token_expires = float(token_expires or 0)
        self._token_checked = False
        self.headers = {}

    def _ensure_token(self):
        """
        Ensures we have a valid access token. Only checks/refreshes once per instance
        unless manually reset via ensure_valid_token().
        """
        if self._token_checked:
            return
        
        self._token_checked = True

        now = time.time()
        if not self.access_token or now >= self.token_expires:
            scopes_all = current_app.config["SCOPE"].split()
            reserved = {"openid", "profile", "offline_access"}
            scopes = [s for s in scopes_all if s not in reserved]

            try:
                result = self.app.acquire_token_by_refresh_token(
                    self.refresh_token, scopes=scopes
                )
            except ValueError as e:
                raise OneDriveServiceError("Token refresh failed")

            if not result or "access_token" not in result:
                raise OneDriveServiceError(
                    result.get("error_description", "Token refresh failed")
                )

            self.access_token = result["access_token"]
            self.refresh_token = result.get("refresh_token", self.refresh_token)
            self.token_expires = now + int(result["expires_in"])

            if not self.user_id and "id_token_claims" in result:
                ext = result["id_token_claims"].get("oid") or result["id_token_claims"].get("sub")
                if ext:
                    from src.models.user_model import User
                    u = User.query.filter_by(ms_id=ext).first()
                    if u:
                        self.user_id = u.id

            if self.user_id:
                save_updated_token(self.user_id, {
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                    "expires_at": self.token_expires,
                })

        self.headers = {"Authorization": f"Bearer {self.access_token}"}

    def ensure_valid_token(self):
        """
        Public method to force token validation if it expires within 5 minutes.
        Resets the _token_checked flag to force a new check.
        """
        # If token expires within 5 minutes, force a refresh
        if (self.token_expires - time.time()) < 300:
            self._token_checked = False
        self._ensure_token()

    def get_auth_url(self, state: str) -> str:
        """Get Microsoft OAuth authorization URL"""
        return self.app.get_authorization_request_url(
            scopes=current_app.config["SCOPE"].split(),
            redirect_uri=current_app.config["REDIRECT_URI"],
            state=state
        )

    def acquire_token_by_code(self, code: str) -> dict:
        """Exchange authorization code for access token"""
        result = self.app.acquire_token_by_authorization_code(
            code,
            scopes=current_app.config["SCOPE"].split(),
            redirect_uri=current_app.config["REDIRECT_URI"]
        )
        if "access_token" not in result:
            raise OneDriveServiceError(
                result.get("error_description", "Auth failed")
            )
        now = time.time()
        self.access_token = result["access_token"]
        self.refresh_token = result.get("refresh_token")
        self.token_expires = now + int(result["expires_in"])
        return result

    def list_root_files(self) -> list:
        """List files and folders in the drive root."""
        self._ensure_token()
        url = f"{self.BASE_URL}/me/drive/root/children"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.json().get("value", [])

    def list_children(self, parent_id: str) -> list:
        """List direct children of a given folder."""
        self._ensure_token()
        url = f"{self.BASE_URL}/me/drive/items/{parent_id}/children"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        items = resp.json().get("value", [])
        items.sort(key=lambda i: ("file" in i, i.get("name", "").lower()))
        return items

    def list_all_files_recursively(self, folder_id=None, _depth=0) -> list:
        """Recursively list all .docx and .txt files under a folder (or root)."""
        if _depth == 0:
            self._ensure_token()
        
        base = (
            f"{self.BASE_URL}/me/drive/items/{folder_id}/children"
            if folder_id else
            f"{self.BASE_URL}/me/drive/root/children"
        )
        all_files = []
        url = base
        while url:
            resp = requests.get(url, headers=self.headers)
            if resp.status_code != 200:
                raise OneDriveServiceError(resp.text)
            data = resp.json()
            for item in data.get("value", []):
                if "folder" in item:
                    try:
                        all_files.extend(
                            self.list_all_files_recursively(item["id"], _depth=_depth + 1)
                        )
                    except OneDriveServiceError:
                        continue
                elif "file" in item:
                    name = item.get("name", "").lower()
                    if name.endswith(".docx") or name.endswith(".txt"):
                        all_files.append(item)
            url = data.get("@odata.nextLink")
        return all_files

    def list_delta(self, delta_link=None) -> tuple:
        """Get delta changes from OneDrive"""
        self._ensure_token()
        url = delta_link or f"{self.BASE_URL}/me/drive/root/delta"
        items = []
        new_delta = None
        while url:
            resp = requests.get(url, headers=self.headers)
            if resp.status_code != 200:
                raise OneDriveServiceError(resp.text)
            data = resp.json()
            items.extend(data.get("value", []))
            url = data.get("@odata.nextLink")
            new_delta = data.get("@odata.deltaLink") or new_delta
        return items, new_delta

    def fetch_file_content(self, file_id: str) -> bytes:
        """Download the raw content of a file as bytes."""
        self._ensure_token()
        resp = requests.get(
            f"{self.BASE_URL}/me/drive/items/{file_id}/content",
            headers=self.headers,
            stream=True
        )
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.content

    def get_item(self, item_id: str) -> dict:
        """Get metadata for a specific item"""
        self._ensure_token()
        url = f"{self.BASE_URL}/me/drive/items/{item_id}"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.json()
 
    def get_embed_link(self, item_id: str) -> str:
        """Get embed link for a file"""
        self._ensure_token()
        url = f"{self.BASE_URL}/me/drive/items/{item_id}/preview"
        resp = requests.post(url, headers=self.headers, json={})
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.json().get("getUrl")

    def get_user_info(self) -> dict:
        """Get current user information"""
        self._ensure_token()
        url = f"{self.BASE_URL}/me"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.json()

    def upload_file_content(self, item_id: str, content: bytes) -> None:
        """Upload content to replace an existing file"""
        self._ensure_token()
        url = f"{self.BASE_URL}/me/drive/items/{item_id}/content"
        # PUT to the /content endpoint replaces the file
        resp = requests.put(url, headers=self.headers, data=content)
        if resp.status_code not in (200, 201):
            raise OneDriveServiceError(f"Upload failed [{resp.status_code}]: {resp.text}")

    def create_edit_link(self, item_id: str) -> str:
        """Create an edit link for a file"""
        self._ensure_token()
        url = f"{self.BASE_URL}/me/drive/items/{item_id}/createLink"
        payload = {"type": "edit", "scope": "anonymous"}
        resp = requests.post(url, headers=self.headers, json=payload)
        if resp.status_code != 200:
            raise OneDriveServiceError(f"Create edit link failed: {resp.text}")
        return resp.json()["link"]["webUrl"]

    def upload_file(
            self,
            filename: str,
            content: bytes,
            parent_folder_id: str = None
    ) -> dict:
        """Upload a new file to OneDrive"""
        self._ensure_token()

        if parent_folder_id:
            url = (
                f"{self.BASE_URL}/me/drive/items/"
                f"{parent_folder_id}:/{filename}:/content"
            )
        else:
            url = f"{self.BASE_URL}/me/drive/root:/{filename}:/content"

        resp = requests.put(
            url,
            headers=self.headers,
            data=content
        )
        if resp.status_code not in (200, 201):
            raise OneDriveServiceError(
                f"Upload failed [{resp.status_code}]: {resp.text}"
            )

        return resp.json()