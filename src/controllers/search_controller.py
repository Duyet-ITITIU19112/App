from src.services.elastic_service import search_bm25
from src.services.expansion_service import expand_query
from src.config.search_config import BM25_TOP_K, SECOND_BM25_TOP_K, EXPANSION_K, FINAL_RESULTS_K, EMBEDDING_TOP_K
from src.services.crossencoder_service import rerank_crossencoder
from src.services.embedding_service import rerank_biencoder
from src.services.text_preprocessing import preprocess_for_encoder


def full_search_pipeline(user_query: str, user_id: int):

    top_500 = search_bm25(user_query, user_id=user_id, top_k=BM25_TOP_K)
    print(f"[DEBUG] BM25_TOP_K = {BM25_TOP_K}")

    print(f"[DEBUG] Index: index_user_{user_id}")
    print(f"[DEBUG] Original user query: '{user_query}'")
    print(f"[DEBUG] Retrieved top_500: {len(top_500)} docs" if top_500 else "[DEBUG] No top docs — returning original query.")

    expanded_bm25_query, expanded_encoder_query = expand_query(user_query, top_500, k=EXPANSION_K)
    print(f"[DEBUG] Expansion input doc count: {len(top_500)}")
    print(f"[DEBUG] expanded query (raw): {expanded_encoder_query}")
    print(f"[DEBUG] expanded query (bm25-ready): {expanded_bm25_query}")

    top_200 = search_bm25(expanded_bm25_query, user_id=user_id, top_k=SECOND_BM25_TOP_K)

    encoder_ready_query = preprocess_for_encoder(expanded_encoder_query)
    print(f"[DEBUG] encoder-ready query: {encoder_ready_query}")

    biencoder_top = rerank_biencoder(encoder_ready_query, top_200, top_k=EMBEDDING_TOP_K)
    reranked = rerank_crossencoder(encoder_ready_query, biencoder_top, top_k=FINAL_RESULTS_K)

    return reranked
