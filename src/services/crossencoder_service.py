from sentence_transformers import CrossEncoder
import torch
from src.config.search_config import CROSS_ENCODER_MODEL_PATH

# Automatically use GPU if available
device = "cuda" if torch.cuda.is_available() else "cpu"

# Load CrossEncoder from local path with correct device
model = CrossEncoder(CROSS_ENCODER_MODEL_PATH, device=device)
model.half()
model.eval()

def rerank_crossencoder(query, docs, top_k=5, batch_size=1024):
    print(f"🔍 Reranking using query: {query}")
    if not docs:
        return []

    pairs = [(query, doc["content"]) for doc in docs]

    # Predict relevance scores with appropriate batch size
    scores = model.predict(pairs, batch_size=batch_size)

    # Attach scores
    for doc, score in zip(docs, scores):
        doc["rerank_score"] = float(score)

    # Sort and return top-K
    reranked = sorted(docs, key=lambda x: x["rerank_score"], reverse=True)
    result = reranked[:top_k]

    # Log top-k results BEFORE return
    print(f"📊 Cross-encoder Top-{len(result)} Results:")
    for i, doc in enumerate(result):  # Show all results since it's final top-k
        score = doc["rerank_score"]
        title = doc.get("title", doc.get("filename", "Untitled"))[:50]
        print(f"  {i + 1}. Score: {score:.4f} | {title}")

    return result