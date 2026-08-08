import json
import logging
import re
from collections.abc import AsyncIterator

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.schemas.telemetry import TelemetryEventIn

logger = logging.getLogger(__name__)
STREAM_ID_PATTERN = re.compile(r"^(\$|0-0|\d+-\d+)$")


class TelemetryStreamCursorError(ValueError):
    pass


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
                maxlen=self.settings.telemetry_stream_maxlen,
                approximate=True,
            )
            return True
        except RedisError as exc:
            logger.warning("redis_publish_failed: %s", exc)
            return False

    def validate_cursor(self, cursor: str) -> str:
        if not STREAM_ID_PATTERN.match(cursor):
            raise TelemetryStreamCursorError("Invalid Redis stream cursor")
        return cursor

    async def latest_id(self) -> str:
        if self._client is None:
            raise RedisError("Redis client is not connected")
        rows = await self._client.xrevrange(self.settings.redis_stream_name, count=1)
        if not rows:
            return "0-0"
        return rows[0][0]

    async def read_batches(
        self,
        cursor: str,
        *,
        block_ms: int = 15_000,
        count: int = 10,
    ) -> AsyncIterator[tuple[str, list[dict[str, object]]]]:
        if self._client is None:
            raise RedisError("Redis client is not connected")
        current = self.validate_cursor(cursor)
        while True:
            response = await self._client.xread(
                {self.settings.redis_stream_name: current},
                count=count,
                block=block_ms,
            )
            if not response:
                yield current, []
                continue
            for _, entries in response:
                for stream_id, fields in entries:
                    current = stream_id
                    payload = fields.get("events")
                    if not isinstance(payload, str):
                        continue
                    decoded = json.loads(payload)
                    if isinstance(decoded, list):
                        yield stream_id, decoded
