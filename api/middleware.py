import json
import os
import time
from datetime import datetime, timezone
from django.conf import settings


class RequestLoggingMiddleware:
    """Logs request/response details and timing per authenticated user to the filesystem."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.log_dir = getattr(settings, "REQUEST_LOG_DIR", settings.BASE_DIR / "logs")
        os.makedirs(self.log_dir, exist_ok=True)

    def __call__(self, request):
        start_dt = datetime.now(timezone.utc)
        start_time = time.monotonic()

        response = self.get_response(request)

        duration = time.monotonic() - start_time
        end_dt = datetime.now(timezone.utc)

        user = getattr(request, "user", None)
        username = user.username if user and user.is_authenticated else "anonymous"

        log_entry = {
            "user": username,
            "method": request.method,
            "path": request.get_full_path(),
            "status_code": response.status_code,
            "start_time": start_dt.isoformat(),
            "end_time": end_dt.isoformat(),
            "duration_seconds": round(duration, 4),
        }

        log_file = self.log_dir / f"{username}.jsonl"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except OSError:
            pass  # never let logging failures break the actual request

        return response

