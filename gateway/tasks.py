import logging

from celery import shared_task

from . import rag
from .models import Chunk, Document
from django.conf import settings

log = logging.getLogger(__name__)
BATCH = 64


@shared_task(name="gateway.ingest_document", queue="ingest", acks_late=True, time_limit=3600)
def ingest_document(doc_id: int) -> None:
    try:
        doc = Document.objects.get(pk=doc_id)
    except Document.DoesNotExist:
        return

    Chunk.objects.filter(document=doc).delete()      # idempotent if the task is retried
    Document.objects.filter(pk=doc.pk).update(status=Document.Status.PROCESSING, error="")

    try:
        existing = Chunk.objects.filter(api_key_id=doc.api_key_id).count()
        total = 0
        for batch in rag.batched(rag.iter_chunks(doc.file.path, doc.filename), BATCH):
            if not Document.objects.filter(pk=doc.pk).exists():
                return                                # deleted while processing
            if existing + total + len(batch) > settings.RAG_MAX_CHUNKS_PER_KEY:
                raise ValueError("This key has reached its document size limit")
            vectors = rag.embed([text for _, text in batch])
            Chunk.objects.bulk_create([
                Chunk(document=doc, api_key_id=doc.api_key_id, position=total + i,
                      page=page, text=text, embedding=vec)
                for i, ((page, text), vec) in enumerate(zip(batch, vectors))
            ])
            total += len(batch)

        if total == 0:
            raise ValueError("No extractable text (scanned PDF? it needs OCR first)")
        Document.objects.filter(pk=doc.pk).update(status=Document.Status.READY, chunk_count=total)
    except Exception as e:
        log.exception("ingest failed for document %s", doc_id)
        Chunk.objects.filter(document_id=doc.pk).delete()
        Document.objects.filter(pk=doc.pk).update(status=Document.Status.FAILED, error=str(e)[:500])