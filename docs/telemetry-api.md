# Observa Telemetry API Contract

This document describes the Phase 2 backend contract. The current frontend simulator is not connected to this backend yet.

## JSON Convention

API JSON uses camelCase to minimize future frontend adaptation. Python internals and database fields use snake_case.

## Telemetry Event

```json
{
  "id": "event-001",
  "timestamp": "2026-08-07T12:00:00Z",
  "service": "api-gateway",
  "region": "us-east",
  "latency": 112.4,
  "throughput": 940.2,
  "cpuUsage": 61.5,
  "memoryUsage": 58.7,
  "errorRate": 0.42,
  "payloadSize": 22184,
  "status": "healthy"
}
```

Supported services: `api-gateway`, `auth-service`, `billing-service`, `search-service`, `worker`.

Supported regions: `us-east`, `us-west`, `eu-central`, `ap-south`.

Supported statuses: `healthy`, `degraded`, `critical`.

## Ingestion

`POST /api/v1/telemetry`

Accepts one event.

`POST /api/v1/telemetry/batch`

```json
{
  "events": []
}
```

Returns:

```json
{
  "acceptedCount": 500,
  "rejectedCount": 0,
  "processingDurationMs": 12.3
}
```

Batch size is capped by `MAX_INGEST_BATCH_SIZE`.

## Metric Query

`GET /api/v1/metrics/query`

Query parameters:

- `start`: optional ISO timestamp
- `end`: optional ISO timestamp
- `service`: optional service filter
- `region`: optional region filter
- `metric`: `latency`, `throughput`, `cpuUsage`, `memoryUsage`, `errorRate`, `payloadSize`
- `aggregation`: `avg`, `min`, `max`, `sum`, `count`
- `bucket`: `raw`, `1m`, `5m`, `1h`

Response:

```json
{
  "metric": "latency",
  "aggregation": "avg",
  "bucket": "1m",
  "points": [
    {
      "timestamp": "2026-08-07T12:00:00Z",
      "value": 108.2,
      "count": 124
    }
  ],
  "processingDurationMs": 4.7,
  "limited": false
}
```

Raw queries are capped by `MAX_QUERY_ROWS`.

## Services

`GET /api/v1/services`

Returns observed service names, the latest timestamp per service, and a recent event count.

## Raw Event Query

`GET /api/v1/telemetry`

Used by `RemoteTelemetrySource` to hydrate and incrementally refresh the frontend `TelemetryStore`.

Supported query parameters:

- `start`
- `end`
- `service`
- `region`
- `limit`

The response is capped by the lower of backend `MAX_QUERY_ROWS` and the raw telemetry hard cap of `10,000` rows. Results are deterministic by `timestamp` and `id`. Without `start`, the endpoint returns the latest capped window in chronological order. With `start`, it returns matching rows from that timestamp forward.

```json
{
  "events": [],
  "limited": false
}
```

## Future Streaming Contract

New ingested batches are published to a Redis Stream named by `REDIS_STREAM_NAME` with camelCase event JSON. A future SSE or WebSocket delivery layer can subscribe to that stream without coupling directly to ingestion.
