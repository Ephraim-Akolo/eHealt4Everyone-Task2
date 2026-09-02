import hashlib
import time

CACHE_TTL_SECONDS = 60


def build_cache_key(request):
    """Cache key that varies by path, query params, user role, and a time bucket —
    so the cache busts automatically on any of: different filters, a role change,
    or simply enough time passing (a new time bucket)."""
    role = "staff" if request.user.is_staff else "user"
    query = sorted(request.GET.items())
    time_bucket = int(time.time() // CACHE_TTL_SECONDS)
    raw_key = f"{request.path}:{query}:{role}:{time_bucket}"
    return "cache:" + hashlib.md5(raw_key.encode()).hexdigest()

