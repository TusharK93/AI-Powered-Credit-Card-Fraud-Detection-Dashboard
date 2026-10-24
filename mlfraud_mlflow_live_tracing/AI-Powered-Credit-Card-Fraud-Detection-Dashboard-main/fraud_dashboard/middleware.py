"""Request correlation and access logging without recording submitted form data."""
import logging
import time
import uuid

logger = logging.getLogger("fraud_dashboard.requests")


class RequestLoggingMiddleware:
    """Attach a per-request ID and emit a concise request completion log."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = uuid.uuid4().hex
        started = time.perf_counter()
        try:
            response = self.get_response(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "request_failed request_id=%s method=%s path=%s duration_ms=%s",
                request.request_id, request.method, request.path, elapsed_ms,
            )
            raise

        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        log_method = logger.warning if response.status_code >= 400 else logger.info
        log_method(
            "request_complete request_id=%s method=%s path=%s status=%s duration_ms=%s",
            request.request_id, request.method, request.path,
            response.status_code, elapsed_ms,
        )
        response["X-Request-ID"] = request.request_id
        return response
