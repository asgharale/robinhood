import logging
import random
from dataclasses import dataclass, field

import httpx
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .counters import incr

log = logging.getLogger(__name__)


class ProviderError(Exception):
    def __init__(self, msg: str, cooldown: int = 30):
        super().__init__(msg)
        self.cooldown = cooldown


class AllProvidersFailed(Exception):
    pass


@dataclass(frozen=True, eq=False)
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str
    daily_limit: int | None = None
    headers: dict = field(default_factory=dict)


SPECS = [
    ("cerebras", "https://api.cerebras.ai/v1", "gemma-4-31b", None, {}),
    ("groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", 950, {}),
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash", 1450, {}),
    ("cloudflare", "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
     "@cf/qwen/qwen2.5-coder-32b-instruct", 9500, {}),
    ("openrouter", "https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free", 180,
     {"X-Title": "Robinhood Gateway"}),
    ("huggingface", "https://router.huggingface.co/v1", "meta-llama/Llama-3.3-70B-Instruct", None, {}),
]


def _build() -> list[list[Provider]]:
    groups = []
    for family, url, model, limit, headers in SPECS:
        keys = settings.LLM_KEYS.get(family, [])
        group = [
            Provider(f"{family}_{i}", url.format(account_id=settings.CLOUDFLARE_ACCOUNT_ID),
                     k, model, limit, headers)
            for i, k in enumerate(keys)
        ]
        if group:
            groups.append(group)
    return groups


GROUPS = _build()

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.LLM_TIMEOUT_SECONDS, connect=5.0),
            limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
            proxy=settings.OUTBOUND_PROXY or None,  # httpx>=0.26 (older versions: proxies=)
        )
    return _client


def _day() -> str:
    return timezone.now().strftime("%Y%m%d")


async def _skip_reason(p: Provider) -> str | None:
    cd, pu = f"cd:{p.name}", f"pu:{p.name}:{_day()}"
    vals = await cache.aget_many([cd, pu])
    if vals.get(cd):
        return "cooldown"
    if p.daily_limit and vals.get(pu, 0) >= p.daily_limit:
        return "quota"
    return None


async def _call(p: Provider, messages: list[dict], max_tokens: int) -> str:
    try:
        r = await get_client().post(
            f"{p.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {p.api_key}", **p.headers},
            json={"model": p.model, "messages": messages, "max_tokens": max_tokens},
        )
    except httpx.TimeoutException:
        raise ProviderError("timeout", 30)
    except httpx.RequestError as e:
        raise ProviderError(f"network: {type(e).__name__}", 30)

    if r.status_code == 429:
        raise ProviderError("rate limited", 60)
    if r.status_code in (401, 403):
        raise ProviderError(f"auth/blocked HTTP {r.status_code}", 3600)
    if r.status_code >= 400:
        raise ProviderError(f"HTTP {r.status_code}: {r.text[:150]}", 30)
    try:
        text = r.json()["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ProviderError("unexpected response shape", 30)
    if not text:
        raise ProviderError("empty content", 10)
    return text


async def complete(messages: list[dict], max_tokens: int) -> tuple[str, str]:
    """Returns (answer, provider_name) or raises AllProvidersFailed."""
    trace = []
    for group in GROUPS:
        for p in random.sample(group, len(group)):
            reason = await _skip_reason(p)
            if reason:
                trace.append(f"{p.name}:{reason}")
                continue
            try:
                text = await _call(p, messages, max_tokens)
            except ProviderError as e:
                await cache.aset(f"cd:{p.name}", 1, e.cooldown)
                trace.append(f"{p.name}:{e}")
                continue
            await incr(f"pu:{p.name}:{_day()}", 90000)
            return text, p.name
    log.error("all providers failed: %s", trace)
    raise AllProvidersFailed