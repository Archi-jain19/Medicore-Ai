"""HTTP middleware: request ids + structured access log, and security headers."""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import request_id_var

log = logging.getLogger("medicore.access")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(self)",
    "Cross-Origin-Opener-Policy": "same-origin",
}
# The API only returns JSON / files; nothing should ever execute in its origin.
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
DOCS_CSP = ("default-src 'self'; img-src 'self' data: https://fastapi.tiangolo.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; script-src 'self' 'unsafe-inline' "
            "https://cdn.jsdelivr.net; frame-ancestors 'none'")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, hsts: bool = False):
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id", "")
        rid = rid if 8 <= len(rid) <= 64 and rid.replace("-", "").isalnum() else uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        finally:
            dur = round((time.perf_counter() - start) * 1000, 1)
            path = request.url.path
            if path not in ("/api/health", "/api/ready"):
                log.info("%s %s %s %.1fms", request.method, path, status, dur,
                         extra={"method": request.method, "path": path, "status": status, "duration_ms": dur,
                                "client": request.client.host if request.client else None})
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        docs = request.url.path.startswith(("/api/docs", "/api/redoc"))
        response.headers.setdefault("Content-Security-Policy", DOCS_CSP if docs else API_CSP)
        if self.hsts:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if not docs:
            response.headers.setdefault("Cache-Control", "no-store")
        return response
