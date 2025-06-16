import time
from src.services.microsoft_graph import MicrosoftGraphService, OneDriveServiceError
from src.services.parser import parse_stream
from src.services.elastic_service import bulk_index_documents  # uses _bulk API
from src.models.document_model import Document


def ingest_user_onedrive_files(user, svc=None):
    if svc is None:
        svc = MicrosoftGraphService(
            access_token=user.access_token,
            refresh_token=user.refresh_token,
            token_expires=user.token_expires.timestamp(),
            user_id=user.id  # ✅ now always set
        )


