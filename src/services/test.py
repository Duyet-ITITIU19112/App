import os
import requests
from msal import PublicClientApplication

# Load environment variables
CLIENT_ID = os.getenv("CLIENT_ID")
TENANT_ID = os.getenv("MS_TENANT_ID")

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["User.Read", "Files.Read"]


def main():
    app = PublicClientApplication(CLIENT_ID, authority=AUTHORITY)

    # Try silent first
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    # Fallback to device code flow if needed
    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            print("Failed to create device flow. Check client ID and tenant.")
            return
        print(flow["message"])
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        token = result["access_token"]
        print("\n✅ Login succeeded! Access token acquired.\n")
    else:
        print("❌ Authentication failed:", result.get("error_description"))
        return

    # Fetch user profile
    resp = requests.get(
        "https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    print("User profile:", resp.json(), "\n")

    # List files in OneDrive root
    resp = requests.get(
        "https://graph.microsoft.com/v1.0/me/drive/root/children",
        headers={"Authorization": f"Bearer {token}"}
    )
    if resp.status_code == 200:
        items = resp.json().get("value", [])
        print("📄 OneDrive root file list:")
        for it in items:
            name = it.get("name")
            typ = 'Folder' if 'folder' in it else 'File'
            print(f" - {name} ({typ})")
    else:
        print("Failed to list files:", resp.text)


if __name__ == "__main__":
    main()
