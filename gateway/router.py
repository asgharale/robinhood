import logging
import random
from dataclasses import dataclass, field

import httpx
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .counters import incr

log = logging.getLogger(__name__)


def pick_free_openrouter_model() -> str | None:
    try:
        r = httpx.get("https://openrouter.ai/api/v1/models", timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
        free = []
        for m in data:
            price = m.get("pricing", {}).get("prompt")
            try:
                is_free = float(price) == 0
            except (TypeError, ValueError):
                is_free = False
            if is_free:
                free.append(m["id"])
        return free[0] if free else None
    except Exception as e:
        log.warning("openrouter model lookup failed: %s", e)
        return None


_OPENROUTER_FALLBACK = "meta-llama/llama-3.2-3b-instruct:free"


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
    # 1. Cerebras: Use a valid model name
    ("cerebras", "https://api.cerebras.ai/v1", "llama-3.3-70b", None, {}),
    
    # 2. Groq: Valid model name (the 401 was just a bad key, fixed in Step 1)
    ("groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", 950, {}),
    
    # 3. Gemini: Use a valid, free-tier compatible model name
    ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-1.5-flash", 1450, {}),
    
    # 4. Cloudflare: Already working perfectly
    ("cloudflare", "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
     "@cf/qwen/qwen2.5-coder-32b-instruct", 9500, {}),
    
    # 5. OpenRouter: Model is None here because your `pick_free_openrouter_model()` handles it dynamically
    ("openrouter", "https://openrouter.ai/api/v1", None, 180, {"X-Title": "Robinhood Gateway"}),
    
    # 6. HuggingFace: SWITCH to a genuinely free model (3B size). 70B requires paid credits now.
    ("huggingface", "https://router.huggingface.co/v1", "meta-llama/Llama-3.2-3B-Instruct", None, {}),
]


def _build() -> list[list[Provider]]:
    groups = []
    openrouter_model = pick_free_openrouter_model() or _OPENROUTER_FALLBACK
    for family, url, model, limit, headers in SPECS:
        actual_model = openrouter_model if family == "openrouter" else model
        keys = settings.LLM_KEYS.get(family, [])
        group = [
            Provider(f"{family}_{i}", url.format(account_id=settings.CLOUDFLARE_ACCOUNT_ID),
                     k, actual_model, limit, headers)
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
