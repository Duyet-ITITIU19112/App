from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
import numpy as np


def expand_query(original_query: str, top_docs: list, k=3):
    """
    TF-IDF based query expansion using relevance feedback from top documents.
    """
    corpus = [doc.get("content", "") for doc in top_docs if doc.get("content")]
    if not corpus:
        # No docs to expand from: return original query
        return original_query.strip(), original_query
    # 1) Fit TF–IDF on the corpus
    vectorizer = TfidfVectorizer(lowercase=True, stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(corpus)  # shape (n_docs, n_features)
    feature_names = np.array(vectorizer.get_feature_names_out())
    # 2) Document frequency for filtering
    doc_freq = np.asarray((tfidf_matrix > 0).sum(axis=0)).ravel()  # document frequency
    # 3) Filter out extremely common terms (appearing in >80% of docs)
    df_mask = doc_freq < max(2, 0.8 * len(corpus))
    if not np.any(df_mask):
        df_mask = np.ones_like(df_mask, dtype=bool)
    # 4) Vectorize the original query in the same TF–IDF space
    query_terms = set(original_query.lower().split())
    query_vec = normalize(vectorizer.transform([original_query]))  # shape (1, n_features)
    # 5) Rocchio relevance feedback formula: α*query + β*relevant_docs
    query_weight = 1.0  # α - weight for original query
    relevant_weight = 0.8  # β - weight for relevant documents
    # Compute centroid of relevant documents (assume all top docs are relevant)
    relevant_centroid = np.asarray(tfidf_matrix.mean(axis=0)).ravel()
    # 6) Apply Rocchio formula and filtering
    rocchio_vector = (query_weight * query_vec.toarray().flatten() +
                      relevant_weight * relevant_centroid)
    combined_score = rocchio_vector * df_mask
    # 7) Select top‐k expansion terms (excluding original query terms)
    valid_mask = np.array([t not in query_terms for t in feature_names])
    sorted_indices = np.argsort(combined_score * valid_mask)[::-1]
    expansions = [feature_names[i] for i in sorted_indices if valid_mask[i]][:k]

    # 8) Fallback if no valid expansions found
    if not expansions:
        fallback = [feature_names[i] for i in sorted_indices[:k]]
        expansions = fallback

    # 9) Build expanded query strings
    expanded_query = (original_query + " " + " ".join(expansions)).strip()

    return expanded_query, expanded_query