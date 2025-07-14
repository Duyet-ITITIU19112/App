from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
import numpy as np
from src.services.text_preprocessing import preprocess_bm25_query

def expand_query(original_query: str, top_docs: list, k=5):
    # Build corpus from the top_docs
    corpus = [doc.get("content", "") for doc in top_docs if doc.get("content")]
    if not corpus:
        # No docs to expand from: just return the BM25‐preprocessed original
        return preprocess_bm25_query(original_query), original_query

    # 1) Fit TF–IDF on the corpus
    vectorizer    = TfidfVectorizer()
    tfidf_matrix  = vectorizer.fit_transform(corpus)           # shape (n_docs, n_features)
    feature_names = np.array(vectorizer.get_feature_names_out())

    # 2) Per‐term stats
    tfidf_means = np.asarray(tfidf_matrix.mean(axis=0)).ravel()       # avg weight of each term
    doc_freq    = np.asarray((tfidf_matrix > 0).sum(axis=0)).ravel()  # document frequency

    # 3) Mask out extremely common terms
    df_mask = doc_freq < max(2, 0.8 * len(corpus))
    if not np.any(df_mask):
        df_mask = np.ones_like(df_mask, dtype=bool)

    # 4) Vectorize the (BM25‐preprocessed) query in the same TF–IDF space
    query_bm25  = preprocess_bm25_query(original_query)
    query_terms = set(query_bm25.split())
    query_vec   = normalize(vectorizer.transform([query_bm25]))       # shape (1, n_features)

    # 5) Compute per‐term “cosine” scores by noticing that
    #    cos(sim(query_vec, e_i)) = query_vec[0, i] when normalized
    cos_scores = query_vec.toarray().flatten()   # length = n_features

    # 6) Combine signals
    combined_score = (0.7 * tfidf_means + 0.3 * cos_scores) * df_mask

    # 7) Pick top‐k new terms (excluding terms already in the query)
    valid_mask     = np.array([t not in query_terms for t in feature_names])
    sorted_indices = np.argsort(combined_score * valid_mask)[::-1]
    expansions     = [feature_names[i] for i in sorted_indices if valid_mask[i]][:k]

    # 8) Fallback in the unlikely event nothing passes
    if not expansions:
        fallback = [feature_names[i] for i in sorted_indices[:k]]
        expansions = fallback

    # 9) Build final strings
    expanded_encoder = (original_query + " " + " ".join(expansions)).strip()
    expanded_bm25    = preprocess_bm25_query(expanded_encoder)

    return expanded_bm25, expanded_encoder
