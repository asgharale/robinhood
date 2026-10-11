import secrets
from datetime import datetime

from asgiref.sync import sync_to_async
from django.conf import settings
from ninja import File, Router, Schema, UploadedFile
from ninja.errors import HttpError
from ninja.security import HttpBearer

from .models import ApiKey, Document
from .rag import SUPPORTED
from .tasks import ingest_document
from .documents import create_document, DocumentOut


class AdminTokenAuth(HttpBearer):
    async def authenticate(self, request, token):
        expected = settings.ADMIN_API_TOKEN
        if expected and secrets.compare_digest(token.encode(), expected.encode()):
            return True
        return None


router = Router(auth=AdminTokenAuth(), tags=["admin"])


class DocumentOut(Schema):
    id: int
    filename: str
    size_bytes: int
    chunk_count: int
    status: str
    error: str
    created_at: datetime


async def _get_key(key_id: int) -> ApiKey:
    try:
        return await ApiKey.objects.aget(pk=key_id)
    except ApiKey.DoesNotExist:
        raise HttpError(404, "API key not found")


@router.post("/keys/{int:key_id}/documents/", response={202: DocumentOut})
async def upload_document(request, key_id: int, file: UploadedFile = File(...)):
    key = await _get_key(key_id)
    return 202, await create_document(key, file, enforce_quota=False)


@router.get("/keys/{int:key_id}/documents/", response=list[DocumentOut])
async def list_documents(request, key_id: int):
    await _get_key(key_id)
    return [d async for d in Document.objects.filter(api_key_id=key_id)]


@router.delete("/keys/{int:key_id}/documents/{int:doc_id}/", response={204: None})
async def delete_document(request, key_id: int, doc_id: int):
    deleted, _ = await Document.objects.filter(pk=doc_id, api_key_id=key_id).adelete()
    if not deleted:
        raise HttpError(404, "Document not found")
    return 204, None


@router.delete("/keys/{int:key_id}/documents/", response={204: None})
async def clear_documents(request, key_id: int):
    await _get_key(key_id)
    await Document.objects.filter(api_key_id=key_id).adelete()
    return 204, None