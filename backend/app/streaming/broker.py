import json
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.schemas.telemetry import TelemetryEventIn

logger = logging.getLogger(__name__)


class TelemetryBroker:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: Redis | None = None

    async def connect(self) -> None:
        self._client = Redis.from_url(self.settings.redis_url, decode_responses=True)
        try:
            await self._client.ping()
        except RedisError as exc:
            logger.warning("redis_connect_failed: %s", exc)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def ready(self) -> bool:
        if self._client is None:
            return False
        await self._client.ping()
        return True

    async def publish(self, events: list[TelemetryEventIn]) -> bool:
        if self._client is None or not events:
            return False
        payload = json.dumps(
            [event.model_dump(mode="json", by_alias=True) for event in events],
            separators=(",", ":"),
        )
        try:
            await self._client.xadd(
                self.settings.redis_stream_name,
                {"events": payload, "count": str(len(events))},
                maxlen=100_000,
                approximate=True,
            )
            return True
        except RedisError as exc:
            logger.warning("redis_publish_failed: %s", exc)
            return False
