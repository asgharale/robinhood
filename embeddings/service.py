import threading

import numpy as np
from django.conf import settings

_model = None
_model_lock = threading.Lock()
_passage_lock = threading.Lock()  # ingestion batches run one at a time; queries never wait for them


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from fastembed import TextEmbedding
                _model = TextEmbedding(
                    model_name=settings.EMBEDDING_MODEL,
                    specific_model_path=settings.EMBED_MODEL_DIR,
                )
    return _model


def embed_blocking(texts: list[str], kind: str) -> np.ndarray:
    """CPU-bound. e5 needs the 'query: ' / 'passage: ' prefix, added here so callers never do it."""
    prefixed = [f"{kind}: {t}" for t in texts]
    m = _get_model()
    if kind == "passage":
        with _passage_lock:
            vecs = list(m.embed(prefixed, batch_size=8))
    else:
        vecs = list(m.embed(prefixed))
    a = np.array(vecs, dtype=np.float32)
    a /= np.linalg.norm(a, axis=1, keepdims=True).clip(min=1e-9)
    return a