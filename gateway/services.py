from django.conf import settings
from django.utils import timezone
from ninja.errors import HttpError

from .counters import incr
from .models import Message
from .router import AllProvidersFailed, complete
from .tokens import estimate_tokens, trim_history


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


async def chat_once(key, text, system_prompt="", max_tokens=None):
    await enforce_limits(key)
    messages = [
        {"role": "system", "content": system_prompt or settings.DEFAULT_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    return await _generate(messages, max_tokens)


async def run_turn(key, conv, text, max_tokens=None):
    await enforce_limits(key)
    rows = [
        m async for m in
        conv.messages.order_by("-id").values("role", "content")[: settings.HISTORY_MAX_MESSAGES]
    ]
    rows.reverse()
    history = trim_history(rows, settings.HISTORY_TOKEN_BUDGET - estimate_tokens(text))
    messages = [
        {"role": "system", "content": conv.system_prompt or settings.DEFAULT_SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": text},
    ]
    answer, provider = await _generate(messages, max_tokens)

    await Message.objects.abulk_create([
        Message(conversation=conv, role=Message.Role.USER, content=text),
        Message(conversation=conv, role=Message.Role.ASSISTANT, content=answer, provider=provider),
    ])
    return answer, provider