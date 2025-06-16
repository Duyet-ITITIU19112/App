import time
from src.services.microsoft_graph import MicrosoftGraphService, OneDriveServiceError
from src.services.parser import parse_stream
from src.services.elastic_service import bulk_index_documents  # uses _bulk API
from src.models.document_model import Document

def ingest_user_onedrive_files(user):
    """
    Ingest all .txt and .docx files from a user's OneDrive:
    - Recursively crawls files
    - Parses and indexes content in batch
    - Saves metadata to SQL (optional)
    """
    svc = MicrosoftGraphService(
        access_token=user.access_token,
        refresh_token=user.refresh_token,
        token_expires=user.token_expires.timestamp() if user.token_expires else 0
    )

    try:
        files = svc.list_all_files_recursively()
    except OneDriveServiceError as e:
        raise OneDriveServiceError(f"❌ Failed to list OneDrive files: {e}")

    batch = []

    for item in files:
        name = item.get("name", "")
        if not name.lower().endswith((".txt", ".docx")):
            continue

        try:
            content_bytes = svc.fetch_file_content(item["id"])
            text = parse_stream(name, content_bytes)
        except Exception as e:
            print(f"⚠️ Skipped '{name}': {e}")
            continue

        # Optional: store document in SQL
        try:
            Document.create_from_onedrive(item, text, user.id)
        except Exception:
            pass  # silently fail for SQL, continue indexing

        batch.append({
            "user_id": user.id,
            "filename": name,
            "content": text
        })

    if batch:
        bulk_index_documents(batch)
        print(f"✅ Indexed {len(batch)} documents for user {user.id}")
    else:
        print(f"⚠️ No documents to index for user {user.id}")
