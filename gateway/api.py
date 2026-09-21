from datetime import datetime
from uuid import UUID

from django.core.cache import cache
from django.utils import timezone
from ninja import Field, NinjaAPI, Schema
from ninja.errors import HttpError
from ninja.security import HttpBearer

from .models import ApiKey, Conversation
from .services import chat_once, run_turn


class ApiKeyAuth(HttpBearer):
    async def authenticate(self, request, token):
        try:
            key = await ApiKey.objects.aget(key=token, is_active=True, user__is_active=True)
        except ApiKey.DoesNotExist:
            return None
        if await cache.aadd(f"lu:{key.id}", 1, 60):  # touch last_used_at at most once a minute
            await ApiKey.objects.filter(pk=key.pk).aupdate(last_used_at=timezone.now())
        return key


api = NinjaAPI(title="Robinhood AI Gateway", version="1", auth=ApiKeyAuth())


# ── Schemas ──────────────────────────────────────────────────────────────
class StartIn(Schema):
    title: str = Field("", max_length=100)
    system_prompt: str = Field("", max_length=2000)
    message: str | None = Field(None, max_length=8000)  # optional first question
    max_tokens: int | None = Field(None, ge=1, le=4096)


class AskIn(Schema):
    message: str = Field(..., min_length=1, max_length=8000)
    max_tokens: int | None = Field(None, ge=1, le=4096)


class ChatIn(AskIn):
    system_prompt: str = Field("", max_length=2000)


class ConversationOut(Schema):
    id: UUID
    title: str
    status: str
    created_at: datetime
    ended_at: datetime | None = None


class StartOut(ConversationOut):
    answer: str | None = None
    provider: str | None = None


class MessageOut(Schema):
    role: str
    content: str
    provider: str
    created_at: datetime


class DetailOut(ConversationOut):
    messages: list[MessageOut]


class AskOut(Schema):
    conversation_id: UUID
    answer: str
    provider: str


class ChatOut(Schema):
    answer: str
    provider: str


class MeOut(Schema):
    daily_limit: int
    used_today: int
    remaining_today: int
    per_minute_limit: int


# ── Helpers ──────────────────────────────────────────────────────────────
async def get_conv(key, conv_id: UUID) -> Conversation:
    try:
        return await Conversation.objects.aget(pk=conv_id, api_key=key)  # scoped to the caller's key
    except Conversation.DoesNotExist:
        raise HttpError(404, "Conversation not found")


# ── Endpoints ────────────────────────────────────────────────────────────
@api.post("/conversations/", response={201: StartOut})
async def start_conversation(request, payload: StartIn):
    key = request.auth
    conv = await Conversation.objects.acreate(
        api_key=key,
        title=(payload.title or payload.message or "")[:100],
        system_prompt=payload.system_prompt,
    )
    answer = provider = None
    if payload.message:
        try:
            answer, provider = await run_turn(key, conv, payload.message, payload.max_tokens)
        except HttpError:
            await conv.adelete()
            raise
    return 201, {
        "id": conv.id, "title": conv.title, "status": conv.status,
        "created_at": conv.created_at, "ended_at": None,
        "answer": answer, "provider": provider,
    }


@api.post("/conversations/{uuid:conv_id}/messages/", response=AskOut)
async def ask(request, conv_id: UUID, payload: AskIn):
    key = request.auth
    conv = await get_conv(key, conv_id)
    if conv.status == Conversation.Status.ENDED:
        raise HttpError(409, "Conversation already ended")
    answer, provider = await run_turn(key, conv, payload.message, payload.max_tokens)
    return {"conversation_id": conv.id, "answer": answer, "provider": provider}


@api.post("/conversations/{uuid:conv_id}/end/", response=ConversationOut)
async def end_conversation(request, conv_id: UUID):
    conv = await get_conv(request.auth, conv_id)
    if conv.status != Conversation.Status.ENDED:
        conv.status = Conversation.Status.ENDED
        conv.ended_at = timezone.now()
        await conv.asave(update_fields=["status", "ended_at"])
    return conv


@api.get("/conversations/", response=list[ConversationOut])
async def list_conversations(request, limit: int = 20, offset: int = 0):
    limit = min(limit, 100)
    qs = Conversation.objects.filter(api_key=request.auth).order_by("-created_at")
    return [c async for c in qs[offset: offset + limit]]


@api.get("/conversations/{uuid:conv_id}/", response=DetailOut)
async def conversation_detail(request, conv_id: UUID):
    conv = await get_conv(request.auth, conv_id)
    msgs = [
        m async for m in
        conv.messages.order_by("id").values("role", "content", "provider", "created_at")
    ]
    return {
        "id": conv.id, "title": conv.title, "status": conv.status,
        "created_at": conv.created_at, "ended_at": conv.ended_at, "messages": msgs,
    }


@api.post("/chat/", response=ChatOut)
async def chat(request, payload: ChatIn):
    """Stateless one-off question, nothing is stored."""
    answer, provider = await chat_once(request.auth, payload.message, payload.system_prompt, payload.max_tokens)
    return {"answer": answer, "provider": provider}


@api.get("/me/", response=MeOut)
async def me(request):
    key = request.auth
    used = await cache.aget(f"rl:{key.id}:d:{timezone.now():%Y%m%d}") or 0
    return {
        "daily_limit": key.daily_limit, "used_today": used,
        "remaining_today": max(0, key.daily_limit - used),
        "per_minute_limit": key.per_minute_limit,
    }