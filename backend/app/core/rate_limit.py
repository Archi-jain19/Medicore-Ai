from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

_s = get_settings()
# Behind nginx, uvicorn runs with --proxy-headers so request.client.host is the real client IP.
limiter = Limiter(
    key_func=get_remote_address,
    enabled=_s.rate_limit_enabled,
    storage_uri=_s.redis_url or "memory://",
    headers_enabled=False,
)
