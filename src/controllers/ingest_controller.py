import time
from src.services.microsoft_graph import MicrosoftGraphService, OneDriveServiceError
from src.services.parser import parse_stream
from src.services.elastic_service import index_document
from src.models.document_model import Document

def ingest_user_onedrive_files(user):
    """
    List and ingest .txt/.docx files from a user's OneDrive:
    - Token refresh handled internally by public methods
    - Parse file content
    - Index into Elasticsearch
    - Store ingestion metadata
    """
    svc = MicrosoftGraphService(
        access_token=user.access_token,
        refresh_token=user.refresh_token,
        token_expires=user.token_expires.timestamp() if user.token_expires else 0
    )

    try:
        files = svc.list_root_files()
    except OneDriveServiceError as e:
        # Provide helpful logging if needed
        raise OneDriveServiceError(f"Failed to list root files: {e}")

    for item in files:
        try:
            content_bytes = svc.fetch_file_content(item["id"])
        except OneDriveServiceError as e:
            raise OneDriveServiceError(f"Failed to fetch file '{item['name']}': {e}")

        text = parse_stream(item["name"], content_bytes)

        # Optionally store metadata using your Document model
        try:
            Document.create_from_onedrive(item, text, user.id)
        except Exception:
            # Logging here if needed, but continue indexing
            pass

        # Index parsed content into Elasticsearch
        index_document(user_id=user.id, filename=item["name"], content=text)
