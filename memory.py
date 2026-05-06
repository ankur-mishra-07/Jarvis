"""
J.A.R.V.I.S. Vector Memory
Long-term semantic memory using FAISS + sentence-transformers.

Stores every user/assistant exchange as an embedding.
Before each query, retrieves the most relevant past exchanges
so Jarvis has accurate long-term recall without sending
the entire conversation history.

Storage: ~/Jarvis/data/memory_faiss/
"""

import os
import json
import time
import threading
import numpy as np

# ─── Config ─────────────────────────────────────────────────────────────────

MEMORY_DIR   = os.path.expanduser("~/Jarvis/data/memory_faiss")
INDEX_FILE   = os.path.join(MEMORY_DIR, "index.faiss")
META_FILE    = os.path.join(MEMORY_DIR, "meta.json")
EMBED_MODEL  = "all-MiniLM-L6-v2"       # 80MB, very fast on M1, 384-dim
MAX_MEMORIES = 5000                       # hard cap — prune oldest beyond this
TOP_K        = 5                          # how many past exchanges to recall

# ─── Lazy-loaded globals ────────────────────────────────────────────────────

_model     = None   # SentenceTransformer
_index     = None   # faiss.IndexFlatIP  (inner product on L2-normed = cosine)
_meta      = []     # list of dicts: {text, role, ts, ...}
_lock      = threading.Lock()
_ready     = False


def _ensure_loaded():
    """Lazy-load the embedding model + FAISS index on first use."""
    global _model, _index, _meta, _ready
    if _ready:
        return
    with _lock:
        if _ready:
            return
        try:
            import faiss
            from sentence_transformers import SentenceTransformer

            print("  [Memory: loading embedding model...]", flush=True)
            _model = SentenceTransformer(EMBED_MODEL)
            dim = _model.get_sentence_embedding_dimension()

            os.makedirs(MEMORY_DIR, exist_ok=True)

            if os.path.exists(INDEX_FILE) and os.path.exists(META_FILE):
                _index = faiss.read_index(INDEX_FILE)
                with open(META_FILE) as f:
                    _meta = json.load(f)
                print(f"  [Memory: loaded {_index.ntotal} memories]", flush=True)
            else:
                _index = faiss.IndexFlatIP(dim)
                _meta = []
                print("  [Memory: fresh index created]", flush=True)

            _ready = True
        except Exception as e:
            print(f"  [Memory init error: {e}]", flush=True)
            _ready = False


def _save():
    """Persist index + metadata to disk."""
    try:
        import faiss
        os.makedirs(MEMORY_DIR, exist_ok=True)
        faiss.write_index(_index, INDEX_FILE)
        with open(META_FILE, "w") as f:
            json.dump(_meta, f)
    except Exception as e:
        print(f"  [Memory save error: {e}]", flush=True)


# ─── Public API ─────────────────────────────────────────────────────────────

def store(user_text, assistant_text, extra=None):
    """
    Store a user↔assistant exchange in vector memory.
    Both sides are embedded together so retrieval gets full context.
    """
    _ensure_loaded()
    if not _ready or not _model:
        return

    # Combine both sides into one chunk for richer retrieval
    combined = f"User: {user_text}\nJarvis: {assistant_text}"
    vec = _model.encode([combined], normalize_embeddings=True)

    with _lock:
        _index.add(np.array(vec, dtype="float32"))
        entry = {
            "user": user_text,
            "assistant": assistant_text,
            "ts": time.time(),
        }
        if extra:
            entry.update(extra)
        _meta.append(entry)

        # Prune oldest if over cap
        if _index.ntotal > MAX_MEMORIES:
            _prune(keep=MAX_MEMORIES - 500)

    # Save in background to not block the voice loop
    threading.Thread(target=_save, daemon=True).start()


def recall(query, k=TOP_K):
    """
    Retrieve the k most relevant past exchanges for a query.
    Returns list of dicts: [{user, assistant, ts, score}, ...]
    """
    _ensure_loaded()
    if not _ready or not _model or _index.ntotal == 0:
        return []

    vec = _model.encode([query], normalize_embeddings=True)
    scores, indices = _index.search(np.array(vec, dtype="float32"), min(k, _index.ntotal))

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0 or idx >= len(_meta):
            continue
        entry = dict(_meta[idx])
        entry["score"] = float(score)
        results.append(entry)

    # Filter out very low relevance (cosine < 0.25)
    results = [r for r in results if r["score"] >= 0.25]
    return results


def recall_formatted(query, k=TOP_K):
    """
    Retrieve relevant memories and format them as a context block
    suitable for injecting into the system prompt.
    """
    memories = recall(query, k)
    if not memories:
        return ""

    lines = ["[Relevant memories from past conversations:]"]
    for m in memories:
        lines.append(f"  User said: {m['user']}")
        lines.append(f"  You replied: {m['assistant']}")
        lines.append("")
    return "\n".join(lines)


def get_stats():
    """Return memory statistics."""
    _ensure_loaded()
    if not _ready:
        return {"status": "not loaded", "count": 0}
    return {
        "status": "ready",
        "count": _index.ntotal if _index else 0,
        "model": EMBED_MODEL,
        "dir": MEMORY_DIR,
    }


def _prune(keep=4500):
    """Remove the oldest memories to stay under the cap."""
    global _index, _meta
    import faiss

    if _index.ntotal <= keep:
        return

    # Keep the most recent `keep` entries
    _meta = _meta[-keep:]

    # Rebuild the FAISS index from scratch with remaining entries
    dim = _model.get_sentence_embedding_dimension()
    new_index = faiss.IndexFlatIP(dim)

    texts = [f"User: {m['user']}\nJarvis: {m['assistant']}" for m in _meta]
    if texts:
        vecs = _model.encode(texts, normalize_embeddings=True, batch_size=64)
        new_index.add(np.array(vecs, dtype="float32"))

    _index = new_index
    print(f"  [Memory: pruned to {_index.ntotal} entries]", flush=True)
