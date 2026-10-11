import os
from datetime import datetime

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.models import Count, Sum
from ninja import File, Router, Schema, UploadedFile
from ninja.errors import HttpError

from .auth import ApiKeyAuth
from .models import Document
from .rag import SUPPORTED
from .tasks import ingest_document

router = Router(auth=ApiKeyAuth(), tags=["documents"])


class DocumentOut(Schema):
    id: int
    filename: str
    size_bytes: int
    chunk_count: int
    status: str
    error: str
    created_at: datetime


class UsageOut(Schema):
    documents: int
    max_documents: int
    storage_mb: float
    max_storage_mb: int


async def create_document(key, file: UploadedFile, enforce_quota: bool = True) -> Document:
    """Shared by the user endpoint and the admin endpoint."""
    name = os.path.basename(file.name)[:255]
    if not name.lower().endswith(SUPPORTED):
        raise HttpError(422, "Only PDF, TXT, MD and DOCX files are supported")
    if file.size > settings.RAG_MAX_FILE_BYTES:
        raise HttpError(413, "File too large")

    if enforce_quota:
        agg = await Document.objects.filter(api_key=key).aaggregate(
            n=Count("id"), total=Sum("size_bytes"))
        if agg["n"] >= key.max_documents:
            raise HttpError(409, f"Document limit reached ({key.max_documents})")
        if (agg["total"] or 0) + file.size > key.max_storage_mb * 1024 * 1024:
            raise HttpError(413, f"Storage limit reached ({key.max_storage_mb} MB)")

    doc = await sync_to_async(Document.objects.create)(
        api_key=key, file=file, filename=name, size_bytes=file.size,
        embedding_model=settings.EMBEDDING_MODEL,
    )
    await sync_to_async(ingest_document.delay)(doc.id)
    return doc


def _manager(request):
    key = request.auth
    if not key.can_manage_documents:
        raise HttpError(403, "Document management is not enabled for this key")
    return key


@router.post("/", response={202: DocumentOut})
async def upload(request, file: UploadedFile = File(...)):
    key = _manager(request)
    return 202, await create_document(key, file)


@router.get("/", response=list[DocumentOut])
async def list_documents(request):
    key = _manager(request)
    return [d async for d in Document.objects.filter(api_key=key)]


@router.get("/usage/", response=UsageOut)
async def usage(request):
    key = _manager(request)
    agg = await Document.objects.filter(api_key=key).aaggregate(
        n=Count("id"), total=Sum("size_bytes"))
    return {
        "documents": agg["n"], "max_documents": key.max_documents,
        "storage_mb": round((agg["total"] or 0) / 1024 / 1024, 2),
        "max_storage_mb": key.max_storage_mb,
    }


@router.get("/{int:doc_id}/", response=DocumentOut)
async def get_document(request, doc_id: int):
    key = _manager(request)
    try:
        return await Document.objects.aget(pk=doc_id, api_key=key)
    except Document.DoesNotExist:
        raise HttpError(404, "Document not found")


@router.delete("/{int:doc_id}/", response={204: None})
async def delete_document(request, doc_id: int):
    key = _manager(request)
    deleted, _ = await Document.objects.filter(pk=doc_id, api_key=key).adelete()
    if not deleted:
        raise HttpError(404, "Document not found")
    return 204, None


@router.delete("/", response={204: None})
async def clear_documents(request):
    key = _manager(request)
    await Document.objects.filter(api_key=key).adelete()
    return 204, None