import hmac
import time

import jwt
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from ninja.security import HttpBearer

from .models import ApiKey

ACCESS, REFRESH = "access", "refresh"


# ── JWT helpers ──────────────────────────────────────────────────────────
def make_token(user, kind: str) -> str:
    now = int(time.time())
    life = settings.JWT_ACCESS_SECONDS if kind == ACCESS else settings.JWT_REFRESH_SECONDS
    return jwt.encode(
        {
            "iss": settings.JWT_ISSUER,
            "sub": str(user.pk),
            "typ": kind,
            "iat": now,
            "exp": now + life,
            "h": user.get_session_auth_hash(),   # changes when the password changes
        },
        settings.JWT_SIGNING_KEY,
        algorithm="HS256",
    )


async def key_from_token(token: str, kind: str) -> ApiKey | None:
    """Valid, unexpired, right type, user active, password unchanged -> the user's ApiKey."""
    try:
        p = jwt.decode(
            token, settings.JWT_SIGNING_KEY, algorithms=["HS256"],
            issuer=settings.JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "typ", "h"]},
        )
        if p["typ"] != kind:
            return None
        key = await ApiKey.objects.select_related("user").aget(
            user_id=int(p["sub"]), is_active=True, user__is_active=True)
    except (jwt.PyJWTError, ApiKey.DoesNotExist, ValueError):
        return None
    if not hmac.compare_digest(p["h"], key.user.get_session_auth_hash()):
        return None
    return key


# ── Auth classes ─────────────────────────────────────────────────────────
class ApiKeyAuth(HttpBearer):
    async def authenticate(self, request, token):
        if not token.startswith("rh_"):
            return None                      # not an API key (probably a JWT)
        try:
            key = await ApiKey.objects.aget(key=token, is_active=True, user__is_active=True)
        except ApiKey.DoesNotExist:
            return None
        if await cache.aadd(f"lu:{key.id}", 1, 60):  # touch last_used_at at most once a minute
            await ApiKey.objects.filter(pk=key.pk).aupdate(last_used_at=timezone.now())
        return key


class JWTAuth(HttpBearer):
    async def authenticate(self, request, token):
        if token.startswith("rh_"):
            return None
        return await key_from_token(token, ACCESS)


# website users send a JWT, programmatic clients send an rh_ API key
USER_AUTH = [JWTAuth(), ApiKeyAuth()]