from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from .cache_utils import build_cache_key, CACHE_TTL_SECONDS


class SampleDataView(APIView):
    """Demonstrates JWT-gated access + Redis caching with dynamic cache-busting."""

    def get(self, request):
        force_refresh = request.GET.get("refresh") == "true"
        cache_key = build_cache_key(request)

        if not force_refresh:
            cached = cache.get(cache_key)
            if cached is not None:
                return Response({**cached, "from_cache": True})

        # Stand-in for an expensive computation / DB query.
        data = {
            "message": "Computed fresh data",
            "requested_by": request.user.username,
            "role": "staff" if request.user.is_staff else "user",
            "params": dict(request.GET),
        }
        cache.set(cache_key, data, timeout=CACHE_TTL_SECONDS)
        return Response({**data, "from_cache": False})

    