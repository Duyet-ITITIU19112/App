import torch
import os
from sentence_transformers import SentenceTransformer,util
from src.config import search_config  # adjust this import if needed

model_path = search_config.BIENCODER_MODEL_PATH

if not os.path.exists(model_path):
    raise RuntimeError(f"❌ Model path does not exist: {model_path}")

# Load the bi-encoder model
biencoder = SentenceTransformer(model_path)


# Choose device
device = "cuda" if torch.cuda.is_available() else "cpu"

# Load model to appropriate device
model = SentenceTransformer(model_path, device=device)

def rerank_biencoder(query, docs, top_k=100):
    if not docs:
        return []

    # Encode query and documents (on GPU if available)
    query_embedding = model.encode(query, convert_to_tensor=True, device=device)
    doc_texts = [doc["content"] for doc in docs]
    doc_embeddings = model.encode(doc_texts, convert_to_tensor=True, device=device)

    # Compute cosine similarity scores
    similarities = util.cos_sim(query_embedding, doc_embeddings)[0]

    # Attach scores to docs
    for doc, score in zip(docs, similarities):
        doc["biencoder_score"] = float(score)

    # Sort and return top K
    reranked = sorted(docs, key=lambda x: x["biencoder_score"], reverse=True)
    return reranked[:top_k]
