import time
import uuid

import redis.asyncio as aioredis
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import get_settings

# Placeholder thresholds — Owner A updates after Tuesday eval run (DECISIONS.md D-006)
_RATE_LIMIT_REQUESTS = 60
_RATE_LIMIT_WINDOW_SECONDS = 60


class TenantRateLimitMiddleware(BaseHTTPMiddleware):
    """Redis token-bucket rate limiter applied to /chat/messages only.

    Key: rate_limit:<tenant_id> — atomic increment with expiry.
    Placeholder: 60 req/min per tenant until eval numbers are in.
    """

    def __init__(self, app, redis_url: str):
        super().__init__(app)
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path != "/chat/messages" or request.method != "POST":
            return await call_next(request)

        tenant_id = self._extract_tenant_id(request)
        if tenant_id is None:
            return await call_next(request)

        allowed = await self._check_rate_limit(tenant_id)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Retry after 60 seconds."},
                headers={"Retry-After": "60"},
            )

        return await call_next(request)

    def _extract_tenant_id(self, request: Request) -> str | None:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        try:
            import jwt
            settings = get_settings()
            payload = jwt.decode(
                auth[7:], settings.JWT_SECRET, algorithms=["HS256"],
                options={"verify_exp": False},
            )
            return payload.get("tenant_id")
        except Exception:
            return None

    async def _check_rate_limit(self, tenant_id: str) -> bool:
        try:
            if self._redis is None:
                self._redis = aioredis.from_url(get_settings().REDIS_URL)
            key = f"rate_limit:{tenant_id}"
            count = await self._redis.incr(key)
            if count == 1:
                await self._redis.expire(key, _RATE_LIMIT_WINDOW_SECONDS)
            return count <= _RATE_LIMIT_REQUESTS
        except Exception:
            return True  # fail open — don't block requests if Redis is unreachable
