from django.core.cache import cache
from django.utils import timezone
from ninja.security import HttpBearer

from .models import ApiKey


class ApiKeyAuth(HttpBearer):
    async def authenticate(self, request, token):
        try:
            key = await ApiKey.objects.aget(key=token, is_active=True, user__is_active=True)
        except ApiKey.DoesNotExist:
            return None
        if await cache.aadd(f"lu:{key.id}", 1, 60):  # touch last_used_at at most once a minute
            await ApiKey.objects.filter(pk=key.pk).aupdate(last_used_at=timezone.now())
        return key