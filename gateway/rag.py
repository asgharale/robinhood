import asyncio
import re
import threading

import numpy as np
from django.conf import settings
from pgvector.django import CosineDistance

from .models import Chunk, Document

# ── Embedding (local, CPU) ───────────────────────────────────────────────
_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                from fastembed import TextEmbedding
                _model = TextEmbedding(
                    model_name=settings.EMBEDDING_MODEL,
                    cache_dir=settings.FASTEMBED_CACHE_DIR,
                )
    return _model


def embed(texts: list[str]) -> np.ndarray:
    """Sync + CPU-bound. Returns an L2-normalized float32 matrix."""
    vecs = np.array(list(_get_model().embed(texts)), dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True).clip(min=1e-9)
    return vecs


# ── Streaming extraction + chunking (used by the Celery task) ────────────
def iter_pages(path: str, filename: str):
    """Yield (page_number | None, text) one page at a time, so memory stays flat."""
    name = filename.lower()
    if name.endswith(".pdf"):
        import pymupdf  # older PyMuPDF versions: import fitz
        with pymupdf.open(path) as pdf:
            for i, page in enumerate(pdf, start=1):
                yield i, page.get_text()
    elif name.endswith((".txt", ".md")):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            yield None, f.read()
    else:
        raise ValueError("Only PDF, TXT and MD files are supported")


def chunk_text(text: str) -> list[str]:
    size, overlap = settings.RAG_CHUNK_SIZE, settings.RAG_CHUNK_OVERLAP
    text = re.sub(r"\s+", " ", text).strip()
    chunks, i = [], 0
    while i < len(text):
        end = min(i + size, len(text))
        if end < len(text):
            cut = text.rfind(" ", i + size // 2, end)  # don't cut mid-word
            if cut != -1:
                end = cut
        chunks.append(text[i:end].strip())
        if end >= len(text):
            break
        i = max(end - overlap, i + 1)
    return [c for c in chunks if c]


def iter_chunks(path: str, filename: str):
    for page, text in iter_pages(path, filename):
        for c in chunk_text(text):
            yield page, c


def batched(iterable, n: int):
    batch = []
    for x in iterable:
        batch.append(x)
        if len(batch) == n:
            yield batch
            batch = []
    if batch:
        yield batch


# ── Retrieval ────────────────────────────────────────────────────────────
async def retrieve(key_id: int, question: str) -> list[str]:
    ready = Document.objects.filter(api_key_id=key_id, status=Document.Status.READY)
    if not await ready.aexists():          # no documents: skip embedding entirely
        return []

    q = (await asyncio.to_thread(embed, [question]))[0]
    rows = [
        r async for r in
        Chunk.objects.filter(api_key_id=key_id, document__status=Document.Status.READY)
        .annotate(dist=CosineDistance("embedding", q))
        .order_by("dist")
        .values_list("document__filename", "page", "text", "dist")[: settings.RAG_TOP_K]
    ]
    rows.sort(key=lambda r: r[3])          # relaxed_order scans can be slightly out of order
    max_dist = 1 - settings.RAG_MIN_SCORE  # cosine distance = 1 - similarity
    return [
        f"[{name}, p.{page}] {text}" if page else f"[{name}] {text}"
        for name, page, text, dist in rows if dist <= max_dist
    ]