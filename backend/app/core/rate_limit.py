import logging

from fastapi import HTTPException, Request, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import Settings

logger = logging.getLogger(__name__)


class RedisRateLimiter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = Redis.from_url(settings.redis_url, decode_responses=True)

    def check(self, request: Request, action: str, limit: int) -> None:
        client_host = request.client.host if request.client else "unknown"
        key = f"rate:auth:{action}:{client_host}"
        try:
            current = self.client.incr(key)
            if current == 1:
                self.client.expire(key, self.settings.auth_rate_limit_window_seconds)
            if current > limit:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many authentication attempts")
        except HTTPException:
            raise
        except RedisError as exc:
            logger.warning("auth_rate_limit_unavailable action=%s error=%s", action, exc)
        finally:
            self.client.close()
