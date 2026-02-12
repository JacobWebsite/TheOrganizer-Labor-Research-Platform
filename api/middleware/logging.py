"""
Structured request logging middleware.

Logs JSON: {method, path, status, duration_ms, client}.
Warns on slow requests (>3s) and 4xx, errors on 5xx.
"""
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("labor_api")

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 1)

        msg = (
            f"{request.method} {request.url.path} "
            f"status={response.status_code} "
            f"duration={duration_ms}ms "
            f"client={_client_ip(request)}"
        )

        if response.status_code >= 500:
            logger.error(msg)
        elif response.status_code >= 400 or duration_ms > 3000:
            logger.warning(msg)
        else:
            logger.info(msg)

        return response
