import time
import traceback
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

        current_app.logger.debug(
            "🔧 MS Graph init: user_id=%s, expires=%.0f (now=%.0f)",
            self.user_id, self.token_expires, time.time()
        )
        if self.user_id is None and not suppress_missing_user_id_warning:
            current_app.logger.warning(
                "❗ MS GraphService created with user_id=None — stack:\n%s",
                "".join(traceback.format_stack(limit=10))
            )

    def _ensure_token(self):
        if self._token_checked:
            return
        self._token_checked = True

        now = time.time()
        if not self.access_token or now >= self.token_expires:
            scopes_all = current_app.config["SCOPE"].split()
            reserved = {"openid", "profile", "offline_access"}
            scopes = [s for s in scopes_all if s not in reserved]
            current_app.logger.debug("🔁 Refreshing token, scopes=%r", scopes)

            try:
                result = self.app.acquire_token_by_refresh_token(
                    self.refresh_token, scopes=scopes
                )
            except ValueError as e:
                current_app.logger.error("❌ Refresh-token error: %s", e)
                raise OneDriveServiceError("Token refresh failed")

            if not result or "access_token" not in result:
                current_app.logger.error("❌ Token refresh failed: %r", result)
                raise OneDriveServiceError(
                    result.get("error_description", "Token refresh failed")
                )

            self.access_token = result["access_token"]
            self.refresh_token = result.get("refresh_token", self.refresh_token)
            self.token_expires = now + int(result["expires_in"])
            current_app.logger.debug("✅ Token refreshed; expires at %.0f", self.token_expires)

            if not self.user_id and "id_token_claims" in result:
                ext = result["id_token_claims"].get("oid") or result["id_token_claims"].get("sub")
                if ext:
                    from src.models.user_model import User
                    u = User.query.filter_by(ms_id=ext).first()
                    if u:
                        self.user_id = u.id
                        current_app.logger.debug(
                            "🔁 Mapped ms_id to user.id=%s", self.user_id
                        )
                    else:
                        current_app.logger.warning(
                            "❗ No local user found for ms_id=%s", ext
                        )

            if self.user_id:
                save_updated_token(self.user_id, {
                    "access_token": self.access_token,
                    "refresh_token": self.refresh_token,
                    "expires_at": self.token_expires,
                })
            else:
                current_app.logger.error(
                    "❌ Token refreshed but user_id missing—token not saved."
                )
        else:
            current_app.logger.debug(
                "🧠 Token still valid for %.0f seconds", self.token_expires - now
            )

        self.headers = {"Authorization": f"Bearer {self.access_token}"}

    def ensure_valid_token(self):
        # If token expires within 5 minutes, force a refresh
        if (self.token_expires - time.time()) < 300:
            self._token_checked = False
        self._ensure_token()

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
            raise OneDriveServiceError(
                result.get("error_description", "Auth failed")
            )
        now = time.time()
        self.access_token = result["access_token"]
        self.refresh_token = result.get("refresh_token")
        self.token_expires = now + int(result["expires_in"])
        return result

    def list_root_files(self) -> list:
        """
        List files and folders in the drive root.
        """
        self._ensure_token()
        url = f"{self.BASE_URL}/me/drive/root/children"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.json().get("value", [])

    def list_children(self, parent_id: str) -> list:
        """
        List direct children of a given folder.
        """
        self._ensure_token()
        url = f"{self.BASE_URL}/me/drive/items/{parent_id}/children"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        items = resp.json().get("value", [])
        items.sort(key=lambda i: ("file" in i, i.get("name", "").lower()))
        return items

    def list_all_files_recursively(self, folder_id=None, _depth=0) -> list:
        """
        Recursively list all .docx and .txt files under a folder (or root).
        """
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
                    except OneDriveServiceError as e:
                        current_app.logger.warning(
                            "⚠️ Skipping folder '%s': %s", item.get("name"), e
                        )
                elif "file" in item:
                    name = item.get("name", "").lower()
                    if name.endswith(".docx") or name.endswith(".txt"):
                        all_files.append(item)
            url = data.get("@odata.nextLink")
        return all_files

    def list_delta(self, delta_link=None) -> tuple:
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
        """
        Download the raw content of a file as bytes.
        """
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

        self._ensure_token()
        url = f"{self.BASE_URL}/me/drive/items/{item_id}"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.json()

    def get_embed_link(self, item_id: str) -> str:

        self._ensure_token()
        url = f"{self.BASE_URL}/me/drive/items/{item_id}/preview"
        resp = requests.post(url, headers=self.headers, json={})
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.json().get("getUrl")

    def get_user_info(self) -> dict:

        self._ensure_token()
        url = f"{self.BASE_URL}/me"
        resp = requests.get(url, headers=self.headers)
        if resp.status_code != 200:
            raise OneDriveServiceError(resp.text)
        return resp.json()

    def upload_file_content(self, item_id: str, content: bytes) -> None:

        self._ensure_token()
        url = f"{self.BASE_URL}/me/drive/items/{item_id}/content"
        # PUT to the /content endpoint replaces the file
        resp = requests.put(url, headers=self.headers, data=content)
        if resp.status_code not in (200, 201):
            raise OneDriveServiceError(f"Upload failed [{resp.status_code}]: {resp.text}")

    def create_edit_link(self, item_id: str) -> str:
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

    def create_subscription(
        self,
        change_type: str,
        resource: str,
        notification_url: str,
        client_state: str,
        expiration_datetime: str
    ) -> dict:
        """
        Create a Graph change-notification subscription.
        """
        url = "https://graph.microsoft.com/v1.0/subscriptions"
        body = {
            "changeType":        change_type,
            "notificationUrl":   notification_url,
            "resource":          resource,
            "clientState":       client_state,
            "expirationDateTime": expiration_datetime
        }
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type":  "application/json"
        }
        resp = requests.post(url, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def renew_subscription(
        self,
        subscription_id: str,
        new_expiration_datetime: str
    ) -> dict:
        """
        Extend an existing subscription’s expiration.
        """
        url = f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}"
        body = {"expirationDateTime": new_expiration_datetime}
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type":  "application/json"
        }
        resp = requests.patch(url, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()
