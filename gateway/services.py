import logging

from django.conf import settings
from django.utils import timezone
from ninja.errors import HttpError

from . import rag
from .counters import incr
from .models import Message
from .router import AllProvidersFailed, complete
from .tokens import estimate_tokens, trim_history

log = logging.getLogger(__name__)


async def enforce_limits(key):
    now = timezone.now()
    if await incr(f"rl:{key.id}:m:{now:%Y%m%d%H%M}", 70) > key.per_minute_limit:
        raise HttpError(429, "Too many requests per minute")
    if await incr(f"rl:{key.id}:d:{now:%Y%m%d}", 90000) > key.daily_limit:
        raise HttpError(429, "Daily request limit reached")


async def _generate(messages, max_tokens):
    try:
        return await complete(messages, max_tokens or settings.LLM_MAX_TOKENS)
    except AllProvidersFailed:
        raise HttpError(503, "All AI providers are busy, please retry in a few seconds")


def build_system_prompt(key, conv_prompt: str = "") -> str:
    """Platform prompt (always) + conversation override, else the key's default, else the fallback."""
    parts = [settings.PLATFORM_SYSTEM_PROMPT,
             conv_prompt or key.system_prompt or settings.DEFAULT_SYSTEM_PROMPT]
    return "\n\n".join(p for p in parts if p)


async def with_context(key, text: str) -> str:
    """Prepend retrieved document chunks. RAG failures never break chat."""
    try:
        chunks = await rag.retrieve(key.id, text)
    except Exception:
        log.exception("RAG failed, answering without context")
        return text
    if not chunks:
        return text
    return ("Use the context below if it is relevant; otherwise answer normally.\n\n"
            "<context>\n" + "\n\n".join(chunks) + "\n</context>\n\nQuestion: " + text)


async def chat_once(key, text, system_prompt="", max_tokens=None):
    await enforce_limits(key)
    messages = [
        {"role": "system", "content": build_system_prompt(key, system_prompt)},
        {"role": "user", "content": await with_context(key, text)},
    ]
    return await _generate(messages, max_tokens)


async def run_turn(key, conv, text, max_tokens=None):
    await enforce_limits(key)
    llm_text = await with_context(key, text)
    rows = [
        m async for m in
        conv.messages.order_by("-id").values("role", "content")[: settings.HISTORY_MAX_MESSAGES]
    ]
    rows.reverse()
    history = trim_history(rows, settings.HISTORY_TOKEN_BUDGET - estimate_tokens(llm_text))
    messages = [
        {"role": "system", "content": build_system_prompt(key, conv.system_prompt)},
        *history,
        {"role": "user", "content": llm_text},
    ]
    answer, provider = await _generate(messages, max_tokens)

    await Message.objects.abulk_create([
        Message(conversation=conv, role=Message.Role.USER, content=text),   # store the original question
        Message(conversation=conv, role=Message.Role.ASSISTANT, content=answer, provider=provider),
    ])
    return answer, provider