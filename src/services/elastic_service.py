from elasticsearch import Elasticsearch, helpers
import os
from dotenv import load_dotenv

load_dotenv()

es = Elasticsearch(
    os.getenv("ELASTICSEARCH_URL", "http://localhost:9200"),
    basic_auth=(os.getenv("ELASTICSEARCH_USERNAME"), os.getenv("ELASTICSEARCH_PASSWORD")),
    verify_certs=False
)

INDEX_NAME = "user_files"

def create_index_if_not_exists():
    if not es.indices.exists(index=INDEX_NAME):
        es.indices.create(index=INDEX_NAME, body={
            "mappings": {
                "properties": {
                    "user_id": {"type": "integer"},
                    "filename": {"type": "text"},
                    "content": {
                        "type": "text",
                        "analyzer": "standard",  # You can replace with "english" if using stemming
                        "term_vector": "with_positions_offsets"  # Required for snippets/highlighting
                    }
                }
            }
        })


def bulk_index_documents(docs: list):
    create_index_if_not_exists()
    actions = [
        {
            "_index": INDEX_NAME,
            "_source": doc
        }
        for doc in docs
    ]
    helpers.bulk(es, actions)


def index_document(user_id: int, filename: str, content: str):
    create_index_if_not_exists()
    doc = {
        "user_id": user_id,
        "filename": filename,
        "content": content,
    }
    es.index(index=INDEX_NAME, document=doc)


def search_bm25(query: str, user_id: int, top_k: int = 100):
    create_index_if_not_exists()

    response = es.search(index=INDEX_NAME, body={
        "size": top_k,
        "query": {
            "bool": {
                "must": [
                    {"match": {"content": query}},
                    {"term": {"user_id": user_id}}
                ]
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
    })

    hits = response.get("hits", {}).get("hits", [])
    return [
        {
            "id": hit["_id"],
            "score": hit["_score"],
            "filename": hit["_source"].get("filename"),
            "snippet": (hit.get("highlight", {}).get("content", [""])[0]).strip(),
            "content": hit["_source"].get("content")  # Optional; remove if not needed
        }
        for hit in hits
    ]
