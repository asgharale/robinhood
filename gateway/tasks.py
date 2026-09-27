import logging
import time

from celery import shared_task
from django.conf import settings

from . import rag
from .models import Chunk, Document

log = logging.getLogger(__name__)
BATCH = 32


def _notify(text: str) -> None:
    """Bale message to the admin. Never lets a notification failure break ingestion."""
    try:
        from external.bale import BaleNotifier   # adjust to your real import path
        BaleNotifier().notify_admin(text)        # adjust to your notifier's real method name
    except Exception:
        log.exception("bale notify failed")


@shared_task(name="gateway.ingest_document", queue="ingest", acks_late=True, time_limit=4 * 3600)
def ingest_document(doc_id: int) -> None:
    try:
        doc = Document.objects.get(pk=doc_id)
    except Document.DoesNotExist:
        return

    Chunk.objects.filter(document=doc).delete()      # idempotent if the task is retried
    Document.objects.filter(pk=doc.pk).update(status=Document.Status.PROCESSING, error="")
    t0 = time.monotonic()

    try:
        existing = Chunk.objects.filter(api_key_id=doc.api_key_id).count()
        total = 0
        for batch in rag.batched(rag.iter_chunks(doc.file.path, doc.filename), BATCH):
            if not Document.objects.filter(pk=doc.pk).exists():
                return                                # deleted while processing
            if existing + total + len(batch) > settings.RAG_MAX_CHUNKS_PER_KEY:
                raise ValueError("This key has reached its document size limit")
            vectors = rag.embed([text for _, text in batch], "passage")
            Chunk.objects.bulk_create([
                Chunk(document=doc, api_key_id=doc.api_key_id, position=total + i,
                      page=page, text=text, embedding=vec)
                for i, ((page, text), vec) in enumerate(zip(batch, vectors))
            ])
            total += len(batch)

        if total == 0:
            raise ValueError("No extractable text (scanned PDF? it needs OCR first)")
        Document.objects.filter(pk=doc.pk).update(status=Document.Status.READY, chunk_count=total)
        _notify(f"✅ {doc.filename} ready: {total} chunks in {time.monotonic() - t0:.0f}s "
                f"(key {doc.api_key_id})")
    except Exception as e:
        log.exception("ingest failed for document %s", doc_id)
        Chunk.objects.filter(document_id=doc.pk).delete()
        Document.objects.filter(pk=doc.pk).update(status=Document.Status.FAILED, error=str(e)[:500])
        _notify(f"❌ {doc.filename} failed (key {doc.api_key_id}): {str(e)[:200]}")