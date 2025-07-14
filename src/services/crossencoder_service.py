from sentence_transformers import CrossEncoder
import torch
from src.config.search_config import CROSS_ENCODER_MODEL_PATH

# Automatically use GPU if available
device = "cuda" if torch.cuda.is_available() else "cpu"

# Load CrossEncoder from local path with correct device
model = CrossEncoder(CROSS_ENCODER_MODEL_PATH, device=device)

def rerank_crossencoder(query, docs, top_k=10):
    print(f"🔍 Reranking using query: {query}")
    if not docs:
        return []

    pairs = [(query, doc["content"]) for doc in docs]

    # Predict relevance scores
    scores = model.predict(pairs)

    # Attach scores
    for doc, score in zip(docs, scores):
        doc["rerank_score"] = float(score)

    # Sort and return top-K
    reranked = sorted(docs, key=lambda x: x["rerank_score"], reverse=True)
    return reranked[:top_k]
