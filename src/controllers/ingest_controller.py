import threading
import tempfile
import os
import hashlib
from datetime import datetime
from dateutil.parser import parse as parse_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import current_app
from src.services.microsoft_graph import MicrosoftGraphService, OneDriveServiceError
from src.services.parser import parse_stream
from src.services.elastic_service import bulk_index_documents, get_indexed_ids_and_hashes
from src.models.document_model import Document
from src.models.user_model import SyncStatus, User
from src.models import db

# Override temp directory (use app config or fallback)
def _init_tempdir():
    temp_dir = os.getenv('TEMP_DIR') or current_app.config.get('TEMP_DIR') or tempfile.gettempdir()
    tempfile.tempdir = temp_dir


def ingest_user_onedrive_files(user: User):
    """
    Fetch and index changed or new .docx/.txt files for a given user.
    Performs a full walk on first run and incremental on subsequent runs, in parallel.
    """
    app = current_app._get_current_object()
    logger = app.logger

    # ─── 1) Build & refresh the Graph service ONCE ───
    svc = MicrosoftGraphService(
        access_token=user.access_token,
        refresh_token=user.refresh_token,
        token_expires=user.token_expires,
        user_id=user.id
    )
    svc.ensure_valid_token()  # only here, once per ingestion

    # persist refreshed tokens
    user.access_token  = svc.access_token
    user.refresh_token = svc.refresh_token
    user.token_expires = datetime.utcfromtimestamp(svc.token_expires)
    db.session.commit()

    # detect first run vs incremental
    start_link = user.delta_link
    first_run = (start_link is None)

    # fetch changes
    changed_files, new_delta = svc.list_delta(start_link)
    logger.info(f"Δ-files for user {user.id}: {len(changed_files)} changes")

    # update delta link
    user.delta_link = new_delta
    db.session.commit()

    if not changed_files:
        logger.info("No changes; exiting immediately.")
        return

    # preload existing docs and hashes
    existing_docs = {doc.file_id: doc for doc in Document.query.filter_by(user_id=user.id)}
    _, es_hashes = get_indexed_ids_and_hashes(user.id)
    all_hashes = {d.content_hash for d in existing_docs.values()}.union(es_hashes)

    docs_to_index = []
    skipped = 0

    def process_item(item):
        # each thread has app context but reuses the single svc
        with app.app_context():
            name = item.get("name", "").lower()
            if not (name.endswith(".docx") or name.endswith(".txt")):
                return None, 0

            fid = item["id"]
            created_at = parse_datetime(item.get("createdDateTime")) if item.get("createdDateTime") else None
            modified_at = parse_datetime(item.get("lastModifiedDateTime")) if item.get("lastModifiedDateTime") else None

            existing = existing_docs.get(fid)
            if not first_run and existing and existing.modified_at == modified_at:
                return None, 1

            try:
                content = svc.fetch_file_content(fid)
                h = hashlib.sha256(content).hexdigest()
                if not first_run and h in all_hashes:
                    return None, 1

                text = parse_stream(name, content).strip()
                if not text:
                    return None, 1

                payload = {
                    "user_id":      user.id,
                    "filename":     item["name"],
                    "content":      text,
                    "source":       "onedrive",
                    "file_id":      fid,
                    "created_at":   created_at,
                    "modified_at":  modified_at,
                    "size":         item.get("size"),
                    "web_url":      item.get("webUrl"),
                    "content_hash": h,
                }

                if not existing:
                    db.session.add(Document(
                        file_id=fid,
                        filename=item["name"],
                        content_hash=h,
                        modified_at=modified_at,
                        user_id=user.id,
                        source="onedrive",
                        web_url=item.get("webUrl"),
                        size=item.get("size"),
                        created_at=created_at
                    ))
                else:
                    existing.filename     = item["name"]
                    existing.content_hash = h
                    existing.modified_at  = modified_at
                    existing.web_url      = item.get("webUrl")
                    existing.size         = item.get("size")

                tmp = os.path.join(tempfile.gettempdir(), f"parsed_user_{user.id}_{fid}.txt")
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass

                return payload, 0

            except OneDriveServiceError as e:
                logger.error(f"OneDrive error on {name}: {e}")
                return None, 0
            except Exception as e:
                logger.warning(f"⚠️ Failed processing {name}: {e}")
                return None, 0

    # parallelize processing
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(process_item, item) for item in changed_files]
        for future in as_completed(futures):
            payload, skip_flag = future.result()
            if skip_flag:
                skipped += skip_flag
            elif payload:
                docs_to_index.append(payload)
                all_hashes.add(payload["content_hash"])

    db.session.commit()
    logger.info(f"✔️ Sync done: indexed {len(docs_to_index)}, skipped {skipped}")

    if docs_to_index:
        bulk_index_documents(docs_to_index, user.id)
        logger.info("✅ Bulk indexing complete")
    else:
        logger.info("📭 Nothing new to index")

def start_user_ingestion_async(user_id: int):
    app = current_app._get_current_object()
    _init_tempdir()
    logger = app.logger
    logger.info(f"🚀 Launching async ingestion for user {user_id}")

    def runner():
        with app.app_context():
            fresh = db.session.get(User, user_id)
            if not fresh:
                logger.warning(f"User {user_id} not found; skipping ingestion")
                return

            fresh.sync_status = SyncStatus.RUNNING
            fresh.sync_updated_at = datetime.utcnow()
            db.session.commit()

            try:
                ingest_user_onedrive_files(fresh)
                fresh.sync_status = SyncStatus.DONE
                fresh.sync_updated_at = datetime.utcnow()
                db.session.commit()
            except OneDriveServiceError as e:
                fresh = db.session.get(User, user_id)
                fresh.sync_status = SyncStatus.ERROR
                fresh.sync_updated_at = datetime.utcnow()
                db.session.commit()
                logger.error("Async ingestion error: %s", e)

    threading.Thread(target=runner, daemon=True).start()
