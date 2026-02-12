"""
In-memory sliding window rate limiter.

Default: 100 requests per 60 seconds per client IP.
Configure via RATE_LIMIT_REQUESTS and RATE_LIMIT_WINDOW env vars.
"""
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..config import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW

# {client_ip: [timestamp, ...]}
_requests: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _cleanup(timestamps: list[float], now: float, window: int) -> list[float]:
    cutoff = now - window
    return [t for t in timestamps if t > cutoff]


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if RATE_LIMIT_REQUESTS <= 0:
            return await call_next(request)

        now = time.time()
        ip = _client_ip(request)
        _requests[ip] = _cleanup(_requests[ip], now, RATE_LIMIT_WINDOW)

        if len(_requests[ip]) >= RATE_LIMIT_REQUESTS:
            retry_after = int(RATE_LIMIT_WINDOW - (now - _requests[ip][0])) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(max(1, retry_after))},
            )

        _requests[ip].append(now)
        return await call_next(request)
