import hashlib
import os
from dotenv import load_dotenv
from flask import current_app
from elasticsearch import Elasticsearch, helpers
from elasticsearch.helpers import BulkIndexError
from dateutil.parser import parse as parse_datetime

from src.models import db, Document
from src.services.microsoft_graph import MicrosoftGraphService
from src.services.parser import parse_stream
from src.services.text_preprocessing import (
    preprocess_bm25_document,
    preprocess_bm25_query
)

load_dotenv()

# In‐process cache of indices we've already ensured exist
_created_indices = set()

def get_es() -> Elasticsearch:
    """Return a configured Elasticsearch client."""
    return Elasticsearch(
        os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"),
        basic_auth=(
            os.getenv("ELASTICSEARCH_USERNAME"),
            os.getenv("ELASTICSEARCH_PASSWORD")
        ),
        verify_certs=False
    )

def get_user_index(user_id: int) -> str:
    """Generate the per-user index name."""
    return f"index_user_{user_id}"

def create_index_if_not_exists(client: Elasticsearch, index_name: str):
    """
    Ensure the given index exists with the correct mappings.
    Uses an in‐process cache to avoid repeated exists() calls.
    """
    if index_name in _created_indices:
        return

    if not client.indices.exists(index=index_name):
        client.indices.create(
            index=index_name,
            body={
                "settings": {
                    "number_of_shards":   1,
                    "number_of_replicas": 0
                },
                "mappings": {
                    "properties": {
                        "user_id":      {"type": "keyword"},
                        "filename": {
                            "type": "text",
                            "fields": {
                                "raw": {"type": "keyword"}
                            }
                        },
                        "content": {
                            "type":           "text",
                            "analyzer":       "english",
                            "term_vector":    "with_positions_offsets"
                        },
                        "content_hash": {"type": "keyword"},
                        "created_at":   {"type": "date"},
                        "modified_at":  {"type": "date"},
                        "size":         {"type": "long"},
                        "web_url":      {"type": "keyword"},
                        "source":       {"type": "keyword"}
                    }
                }
            }
        )
        current_app.logger.info(f"✅ Created index {index_name} with mappings")
    else:
        current_app.logger.debug(f"Index {index_name} already exists")

    _created_indices.add(index_name)

def bulk_index_documents(docs: list, user_id: int):
    client = get_es()
    index_name = get_user_index(user_id)
    create_index_if_not_exists(client, index_name)

    current_app.logger.debug(f"🛠 bulk_index_documents() called with {len(docs)} docs for user {user_id}")

    actions = []
    for doc in docs:
        try:
            source = { **doc }
            source["content"] = preprocess_bm25_document(source.get("content", ""))
            actions.append({
                "_op_type": "index",
                "_index": index_name,
                "_id": doc["file_id"],
                "_source": source
            })
        except Exception as e:
            current_app.logger.error(f"❌ Error preparing doc {doc.get('file_id')}: {e}")

    if not actions:
        current_app.logger.info("📭 No documents to bulk-index.")
        return

    current_app.logger.debug(f"Sample action: {actions[0]}")

    try:
        success, errors = helpers.bulk(
            client,
            actions,
            raise_on_error=False,
            stats_only=True,
            request_timeout=30
        )
        current_app.logger.info(f"✅ Bulk indexed {success} docs for user {user_id}")
        if errors:
            current_app.logger.warning(f"❌ Bulk errors ({len(errors)}): {errors[:3]} …")
    except BulkIndexError as be:
        current_app.logger.error(f"🚨 BulkIndexError for user {user_id}: {be}")
    except Exception as e:
        current_app.logger.error(f"🚨 Exception in bulk_index_documents: {e}")

def search_bm25(query: str, user_id: int, top_k: int):
    client = get_es()
    index_name = get_user_index(user_id)
    # no longer calling create_index_if_not_exists here

    q = preprocess_bm25_query(query)
    current_app.logger.debug(f"🔍 search_bm25 on {index_name} with query '{q}', top_k={top_k}")

    body = {
        "size": top_k,
        "query": {
            "multi_match": {
                "query": q,
                "fields": ["content^2", "filename"]
            }
        },
        "highlight": {
            "fields": {
                "content": {
                    "fragment_size": 150,
                    "number_of_fragments": 1,
                    "pre_tags": ["<mark>"],
                    "post_tags": ["</mark>"]
                }
            }
        }
    }

    response = client.search(index=index_name, body=body)
    hits = response.get("hits", {}).get("hits", [])
    results = []
    for hit in hits:
        src = hit["_source"]
        snippet = hit.get("highlight", {}).get("content", [""])[0]
        results.append({
            "id": hit["_id"],
            "score": hit["_score"],
            "filename": src.get("filename"),
            "snippet": snippet.strip(),
            "content": src.get("content")
        })
    return results

def ingest_single_onedrive_file(user, item):
    name = item.get("name", "").lower()
    if not name.endswith((".docx", ".txt")):
        return

    svc = MicrosoftGraphService(
        access_token=user.access_token,
        refresh_token=user.refresh_token,
        token_expires=user.token_expires,
        user_id=user.id
    )

    fid = item["id"]
    content_bytes = svc.fetch_file_content(fid)
    h = hashlib.sha256(content_bytes).hexdigest()

    existing = Document.query.filter_by(user_id=user.id, file_id=fid).first()
    db_hashes, es_hashes = get_indexed_ids_and_hashes(user.id)
    if h in db_hashes or h in es_hashes:
        return

    text = parse_stream(name, content_bytes).strip()
    if not text:
        return

    created = parse_datetime(item.get("createdDateTime")) if item.get("createdDateTime") else None
    modified = parse_datetime(item.get("lastModifiedDateTime")) if item.get("lastModifiedDateTime") else None

    if not existing:
        doc = Document(
            user_id=user.id,
            file_id=fid,
            filename=item["name"],
            created_at=created,
            modified_at=modified,
            size=item.get("size"),
            web_url=item.get("webUrl"),
            content_hash=h,
            source="onedrive"
        )
        db.session.add(doc)
    else:
        existing.filename     = item["name"]
        existing.modified_at  = modified
        existing.size         = item.get("size")
        existing.web_url      = item.get("webUrl")
        existing.content_hash = h

    db.session.commit()

    single_doc = {
        "user_id":      user.id,
        "file_id":      fid,
        "filename":     item["name"],
        "created_at":   created,
        "modified_at":  modified,
        "size":         item.get("size"),
        "web_url":      item.get("webUrl"),
        "content_hash": h,
        "content":      preprocess_bm25_document(text),
        "source":       "onedrive",
    }

    client = get_es()
    index_name = get_user_index(user.id)
    create_index_if_not_exists(client, index_name)
    client.index(index=index_name, id=fid, body=single_doc)

def get_indexed_ids_and_hashes(user_id: int):
    client = get_es()
    index_name = get_user_index(user_id)
    create_index_if_not_exists(client, index_name)

    body = {
        "_source": ["file_id", "content_hash"],
        "query": {"match_all": {}},
        "size": 10000
    }
    try:
        resp = client.search(index=index_name, body=body)
        hits = resp["hits"]["hits"]
        ids    = { h["_source"]["file_id"]    for h in hits if "file_id"    in h["_source"] }
        hashes = { h["_source"]["content_hash"] for h in hits if "content_hash" in h["_source"] }
        return ids, hashes
    except Exception as e:
        current_app.logger.warning(f"⚠️ ES read failed for {index_name}: {e}")
        return set(), set()
