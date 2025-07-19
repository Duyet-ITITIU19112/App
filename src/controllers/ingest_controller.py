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

    logger.info(f"🔍 DEBUG: Starting ingestion for user {user.id}")

    # ─── 1) Build & refresh the Graph service ONCE ───
    try:
        svc = MicrosoftGraphService(
            access_token=user.access_token,
            refresh_token=user.refresh_token,
            token_expires=user.token_expires,
            user_id=user.id
        )
        svc.ensure_valid_token()  # only here, once per ingestion
        logger.info(f"🔍 DEBUG: Graph service initialized and token validated")
    except Exception as e:
        logger.error(f"🔍 DEBUG: Failed to initialize Graph service: {e}")
        raise

    # persist refreshed tokens
    user.access_token = svc.access_token
    user.refresh_token = svc.refresh_token
    user.token_expires = datetime.utcfromtimestamp(svc.token_expires)
    db.session.commit()

    # detect first run vs incremental
    start_link = user.delta_link
    first_run = (start_link is None)

    # fetch changes
    try:
        changed_files, new_delta = svc.list_delta(start_link)
        logger.info(f"🔍 DEBUG: Found {len(changed_files)} changes (first_run: {first_run})")
    except Exception as e:
        logger.error(f"🔍 DEBUG: Failed to fetch delta changes: {e}")
        raise

    # update delta link
    user.delta_link = new_delta
    db.session.commit()

    if not changed_files:
        logger.info("🔍 DEBUG: No changes found; exiting")
        return

    # preload existing docs and hashes
    existing_docs = {doc.file_id: doc for doc in Document.query.filter_by(user_id=user.id)}
    _, es_hashes = get_indexed_ids_and_hashes(user.id)
    all_hashes = {d.content_hash for d in existing_docs.values()}.union(es_hashes)

    docs_to_index = []
    docs_to_save = []  # NEW: Store document data for database operations
    skipped = 0

    def process_item(item):
        # FIXED: Remove database operations from threads
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
                    "user_id": user.id,
                    "filename": item["name"],
                    "content": text,
                    "source": "onedrive",
                    "file_id": fid,
                    "created_at": created_at,
                    "modified_at": modified_at,
                    "size": item.get("size"),
                    "web_url": item.get("webUrl"),
                    "content_hash": h,
                }

                # NEW: Return document data instead of doing database operations
                doc_data = {
                    "file_id": fid,
                    "filename": item["name"],
                    "content_hash": h,
                    "modified_at": modified_at,
                    "user_id": user.id,
                    "source": "onedrive",
                    "web_url": item.get("webUrl"),
                    "size": item.get("size"),
                    "created_at": created_at,
                    "is_new": existing is None,
                    "existing_doc": existing
                }

                tmp = os.path.join(tempfile.gettempdir(), f"parsed_user_{user.id}_{fid}.txt")
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass

                return payload, doc_data, 0

            except OneDriveServiceError as e:
                logger.error(f"OneDrive error on {name}: {e}")
                return None, None, 0
            except Exception as e:
                logger.warning(f"⚠️ Failed processing {name}: {e}")
                return None, None, 0

    # parallelize processing
    logger.info(f"🔍 DEBUG: Starting parallel processing of {len(changed_files)} files")
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(process_item, item) for item in changed_files]
        for future in as_completed(futures):
            result = future.result()
            if len(result) == 3:  # payload, doc_data, skip_flag
                payload, doc_data, skip_flag = result
                if skip_flag:
                    skipped += skip_flag
                elif payload and doc_data:
                    docs_to_index.append(payload)
                    docs_to_save.append(doc_data)
                    all_hashes.add(payload["content_hash"])
            else:  # Old format for skipped items
                payload, skip_flag = result
                if skip_flag:
                    skipped += skip_flag

    # FIXED: Do all database operations in main thread
    logger.info(f"🔍 DEBUG: Saving {len(docs_to_save)} documents to database")
    for doc_data in docs_to_save:
        if doc_data["is_new"]:
            # Create new document
            new_doc = Document(
                file_id=doc_data["file_id"],
                filename=doc_data["filename"],
                content_hash=doc_data["content_hash"],
                modified_at=doc_data["modified_at"],
                user_id=doc_data["user_id"],
                source=doc_data["source"],
                web_url=doc_data["web_url"],
                size=doc_data["size"],
                created_at=doc_data["created_at"]
            )
            db.session.add(new_doc)
            logger.info(f"🔍 DEBUG: Added new document: {doc_data['filename']}")
        else:
            # Update existing document
            existing = doc_data["existing_doc"]
            existing.filename = doc_data["filename"]
            existing.content_hash = doc_data["content_hash"]
            existing.modified_at = doc_data["modified_at"]
            existing.web_url = doc_data["web_url"]
            existing.size = doc_data["size"]
            logger.info(f"🔍 DEBUG: Updated existing document: {doc_data['filename']}")

    # Commit all database changes
    db.session.commit()
    logger.info(f"🔍 DEBUG: Database commit completed for {len(docs_to_save)} documents")

    # Verify database save
    doc_count = Document.query.filter_by(user_id=user.id).count()
    logger.info(f"🔍 DEBUG: Total documents in database for user {user.id}: {doc_count}")

    logger.info(f"✔️ Sync done: indexed {len(docs_to_index)}, skipped {skipped}")

    if docs_to_index:
        logger.info(f"🔍 DEBUG: Bulk indexing {len(docs_to_index)} documents")
        bulk_index_documents(docs_to_index, user.id)
        logger.info("✅ Bulk indexing complete")
    else:
        logger.info("📭 Nothing new to index")


def start_user_ingestion_async(user_id: int):
    app = current_app._get_current_object()
    _init_tempdir()
    logger = app.logger
    logger.info(f"🚀 DEBUG: start_user_ingestion_async called for user {user_id}")

    def runner():
        logger.info(f"🔍 DEBUG: Background thread started for user {user_id}")
        with app.app_context():
            fresh = db.session.get(User, user_id)
            if not fresh:
                logger.warning(f"🔍 DEBUG: User {user_id} not found; skipping")
                return

            fresh.sync_status = SyncStatus.RUNNING
            fresh.sync_updated_at = datetime.utcnow()
            db.session.commit()
            logger.info(f"🔍 DEBUG: Set sync status to RUNNING for user {user_id}")

            try:
                ingest_user_onedrive_files(fresh)
                fresh.sync_status = SyncStatus.DONE
                fresh.sync_updated_at = datetime.utcnow()
                db.session.commit()
                logger.info(f"🔍 DEBUG: Ingestion completed successfully for user {user_id}")
            except Exception as e:
                logger.error(f"🔍 DEBUG: Ingestion failed for user {user_id}: {e}")
                fresh = db.session.get(User, user_id)
                fresh.sync_status = SyncStatus.ERROR
                fresh.sync_updated_at = datetime.utcnow()
                db.session.commit()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    logger.info(f"🔍 DEBUG: Background thread started for user {user_id}")