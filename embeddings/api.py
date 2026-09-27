import asyncio
import secrets
from typing import Literal

from django.conf import settings
from ninja import Field, Router, Schema
from ninja.errors import HttpError
from ninja.security import HttpBearer

from . import service


class InternalAuth(HttpBearer):
    async def authenticate(self, request, token):
        expected = settings.INTERNAL_TOKEN
        if expected and secrets.compare_digest(token.encode(), expected.encode()):
            return True
        return None


router = Router(auth=InternalAuth())


class EmbedIn(Schema):
    texts: list[str] = Field(..., min_length=1, max_length=64)
    kind: Literal["query", "passage"] = "passage"


@router.post("/embed/", include_in_schema=False)
async def embed(request, payload: EmbedIn):
    if not settings.SERVE_EMBEDDER:      # only the dedicated embedder process answers
        raise HttpError(404, "Not found")
    arr = await asyncio.to_thread(service.embed_blocking, payload.texts, payload.kind)
    return {"vectors": arr.tolist()}