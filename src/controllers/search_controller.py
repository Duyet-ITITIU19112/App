# src/controllers/search_controller.py

from src.services.elastic_service import search_bm25
from src.services.expansion_service import expand_query
from src.services.crossencoder_service import rerank_results
from src.services.text_preprocessing import (
    preprocess_for_bm25,
    preprocess_for_embedding
)

def run_search(query: str, user_id: str):
    # Step 1: Stemmed BM25 search
    bm25_query = preprocess_for_bm25(query)
    bm25_hits = search_bm25(query=bm25_query, user_id=user_id)

    # Step 2: Embedding for expansion
    embedding_query = preprocess_for_embedding(query)
    expansion_terms = expand_query(embedding_query, bm25_hits)

    # Step 3: Rerank the results
    reranked = rerank_results(embedding_query, expansion_terms, bm25_hits)

    # Step 4: Return formatted results for onedrive_browser.html
    return [
        {
            "id": doc["_id"],
            "name": doc["_source"]["name"],
            "snippet": doc["_source"].get("snippet", ""),
            "folder": False
        }
        for doc in reranked
    ]
