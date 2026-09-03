import hashlib
import time

from django.conf import settings
from django.core.cache import cache

CACHE_TIME_BUCKET_SECONDS = getattr(settings, 'CACHE_TIME_BUCKET_SECONDS', 300)
CACHE_VERSION_PREFIX = 'cache_version'


def _version_key(namespace: str, user_id: int) -> str:
    return f"{CACHE_VERSION_PREFIX}:{namespace}:{user_id}"


def get_cache_version(namespace: str, user_id: int) -> int:
    key = _version_key(namespace, user_id)
    version = cache.get(key)
    if version is None:
        version = 1
        cache.set(key, version, timeout=None)
    return version


def bump_cache_version(namespace: str, user_id: int) -> None:
    """Invalidate every cached response for this user/namespace by
    incrementing the version counter that's baked into their cache keys."""
    key = _version_key(namespace, user_id)
    try:
        cache.incr(key)
    except ValueError:
        # Key didn't exist yet (nothing was cached for this user before).
        cache.set(key, 2, timeout=None)


def build_cache_key(request, namespace: str = 'tasks') -> str:
    user = request.user
    role = getattr(getattr(user, 'profile', None), 'role', 'member')
    version = get_cache_version(namespace, user.id)

    query_params = '&'.join(
        f"{k}={v}" for k, v in sorted(request.GET.items()) if k != 'nocache'
    )
    time_bucket = int(time.time() // CACHE_TIME_BUCKET_SECONDS)

    raw_key = (
        f"{namespace}:user:{user.id}:role:{role}:"
        f"v{version}:t{time_bucket}:{query_params}"
    )
    # Hash it so it's a fixed-length, Redis-safe key regardless of how
    # many/long the query params are.
    return f"{namespace}:{hashlib.sha256(raw_key.encode()).hexdigest()}"
