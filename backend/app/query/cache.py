from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.query.schemas import TelemetryQueryRequest, TelemetryQueryResponse

logger = logging.getLogger(__name__)
QUERY_CACHE_NAMESPACE = "observa:query:v1"


@lru_cache(maxsize=8)
def redis_client(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, decode_responses=True)


class RedisQueryCache:
    def __init__(self, settings: Settings) -> None:
        self.client = redis_client(settings.redis_url)
        self.ttl_seconds = settings.query_cache_ttl_seconds
        self.max_bytes = settings.query_cache_max_bytes

    def build_key(
        self,
        *,
        workspace_id: str,
        request: TelemetryQueryRequest,
        start: datetime,
        end: datetime,
        max_points: int,
        max_groups: int,
    ) -> str:
        canonical = {
            "workspaceId": workspace_id,
            "metric": request.metric,
            "aggregation": request.aggregation,
            "bucket": request.bucket,
            "groupBy": request.group_by,
            "filters": request.filters.model_dump(mode="json", by_alias=True, exclude_none=True),
            "start": self._utc_iso(start),
            "end": self._utc_iso(end),
            "limit": request.limit,
            "maxPoints": max_points,
            "maxGroups": max_groups,
        }
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return f"{QUERY_CACHE_NAMESPACE}:{digest}"

    def get(self, key: str) -> TelemetryQueryResponse | None:
        try:
            raw = self.client.get(key)
        except RedisError as exc:
            logger.warning("query_cache_get_failed key=%s error=%s", self._safe_key(key), exc)
            return None
        if raw is None:
            return None
        try:
            return TelemetryQueryResponse.model_validate_json(raw)
        except Exception as exc:
            logger.warning("query_cache_decode_failed key=%s error=%s", self._safe_key(key), exc)
            self.delete(key)
            return None

    def set(self, key: str, response: TelemetryQueryResponse) -> bool:
        payload = json.dumps(response.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":"))
        if len(payload.encode("utf-8")) > self.max_bytes:
            logger.info("query_cache_set_skipped_large key=%s bytes=%s max_bytes=%s", self._safe_key(key), len(payload), self.max_bytes)
            return False
        try:
            self.client.setex(key, self.ttl_seconds, payload)
            return True
        except RedisError as exc:
            logger.warning("query_cache_set_failed key=%s error=%s", self._safe_key(key), exc)
            return False

    def delete(self, key: str) -> None:
        try:
            self.client.delete(key)
        except RedisError as exc:
            logger.warning("query_cache_delete_failed key=%s error=%s", self._safe_key(key), exc)

    @staticmethod
    def _utc_iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _safe_key(key: str) -> str:
        return key[:32] + "..." if len(key) > 32 else key


def response_size_bytes(response: TelemetryQueryResponse) -> int:
    return len(json.dumps(response.model_dump(mode="json", by_alias=True), separators=(",", ":")).encode("utf-8"))
