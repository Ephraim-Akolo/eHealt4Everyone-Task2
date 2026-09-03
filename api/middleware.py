import json
import os
import time
from datetime import datetime, timezone
from django.conf import settings

SENSITIVE_FIELDS = {'password', 'password2', 'token', 'access', 'refresh'}
SENSITIVE_HEADERS = {'HTTP_AUTHORIZATION', 'HTTP_COOKIE'}
LOGGABLE_CONTENT_TYPES = ('application/json',)


class RequestLoggingMiddleware:
    """Logs every request/response, with start/end timestamps and total
    processing duration, to a plain-text (JSON-lines) file per user under
    settings.REQUEST_LOG_DIR, e.g. logs/alice.log, logs/anonymous.log.

    One JSON object per line keeps it easy to both read by eye and to
    parse later (e.g. `jq` or a log shipper), while staying dependency-free.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.log_dir = str(settings.REQUEST_LOG_DIR)
        os.makedirs(self.log_dir, exist_ok=True)

    def __call__(self, request):
        start_perf = time.perf_counter()
        start_dt = datetime.now(timezone.utc)

        request_body = self._read_request_body(request)

        response = self.get_response(request)

        end_perf = time.perf_counter()
        end_dt = datetime.now(timezone.utc)
        duration_ms = round((end_perf - start_perf) * 1000, 2)

        entry = {
            "start_time": start_dt.isoformat(timespec='milliseconds'),
            "end_time": end_dt.isoformat(timespec='milliseconds'),
            "duration_ms": duration_ms,
            "user": self._username(request),
            "method": request.method,
            "path": request.path,
            "query_params": dict(request.GET.items()),
            "status_code": getattr(response, 'status_code', None),
            "request_body": request_body,
            "response_body": self._read_response_body(response),
            "remote_addr": request.META.get('REMOTE_ADDR'),
        }

        self._write_log(entry)
        return response

    def _username(self, request):
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            return user.username
        return 'anonymous'

    def _redact(self, data):
        if isinstance(data, dict):
            return {
                k: ('***REDACTED***' if k.lower() in SENSITIVE_FIELDS else self._redact(v))
                for k, v in data.items()
            }
        if isinstance(data, list):
            return [self._redact(item) for item in data]
        return data

    def _read_request_body(self, request):
        if request.content_type not in LOGGABLE_CONTENT_TYPES:
            return None
        try:
            if not request.body:
                return None
            return self._redact(json.loads(request.body))
        except Exception:
            return None

    def _read_response_body(self, response):
        content_type = response.get('Content-Type', '') if hasattr(response, 'get') else ''
        if 'application/json' not in content_type:
            return None
        try:
            if getattr(response, 'streaming', False):
                return None
            return self._redact(json.loads(response.content))
        except Exception:
            return None

    def _write_log(self, entry):
        safe_username = ''.join(
            c if (c.isalnum() or c in '-_.') else '_' for c in entry['user']
        ) or 'anonymous'
        log_file = os.path.join(self.log_dir, f"{safe_username}.log")
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            pass
