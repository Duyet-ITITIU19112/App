import torch
from torch.cuda.amp import autocast
from sentence_transformers import SentenceTransformer, util
from src.config.search_config import BIENCODER_MODEL_PATH

# ─── Load & prepare model (once at startup) ─────────────────────────────────

device = "cuda" if torch.cuda.is_available() else "cpu"
model  = SentenceTransformer(BIENCODER_MODEL_PATH, device=device)

# 1) Switch to eval mode immediately (fast)
model.eval()

# ─── Reranker ────────────────────────────────────────────────────────────────

def rerank_biencoder(query, docs, top_k=20, batch_size=1024):
    print(f"🔍 Reranking using query: {query}")
    if not docs:
        return []

    texts = [d["content"] for d in docs]

    # 2) Mixed-precision + no_grad block
    with torch.no_grad(), autocast():
        q_emb = model.encode(
            query,
            convert_to_tensor=True,
            device=device
        )
        d_emb = model.encode(
            texts,
            convert_to_tensor=True,
            device=device,
            batch_size=batch_size
        )

    # 3) One-shot GPU cosine + top_k
    hits = util.semantic_search(
        q_emb,
        d_emb,
        top_k=top_k,
        score_function=util.cos_sim
    )[0]

    # 4) Map back into your docs and log top-5
    reranked = []
    for hit in hits:
        idx                 = hit["corpus_id"]
        docs[idx]["score"]  = float(hit["score"])
        reranked.append(docs[idx])

    print(f"📊 Bi-encoder Top-{len(reranked)} Results:")
    for i, doc in enumerate(reranked[:5]):
        sc    = doc["score"]
        title = doc.get("title", doc.get("filename", "Untitled"))[:50]
        print(f"  {i+1}. {sc:.4f} | {title}")
    if len(reranked) > 5:
        print(f"  ... and {len(reranked)-5} more")

    return reranked
