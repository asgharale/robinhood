from django.core.cache import cache


async def incr(key: str, ttl: int) -> int:
    await cache.aadd(key, 0, ttl)
    try:
        return await cache.aincr(key)
    except ValueError:
        await cache.aset(key, 1, ttl)
        return 1