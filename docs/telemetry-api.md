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

New ingested batches are published to a Redis Stream named by `REDIS_STREAM_NAME` with camelCase event JSON. PostgreSQL remains the source of historical truth; Redis is the recent live transport and replay buffer.

## Live SSE Stream

`GET /api/v1/telemetry/stream/cursor`

Returns the current Redis Stream id:

```json
{
  "cursor": "1723050000000-0"
}
```

`GET /api/v1/telemetry/stream?cursor=<redis-stream-id>`

Streams raw telemetry batches as Server-Sent Events:

```text
id: 1723050000001-0
event: telemetry
data: {"events":[...]}
```

Resume semantics:

- The frontend first captures `/stream/cursor`, then hydrates recent history over HTTP, then opens SSE from that cursor.
- Events ingested after the cursor are replayed from Redis, closing the hydration-to-stream race.
- Browser reconnects can use SSE `Last-Event-ID`; the endpoint also accepts `cursor`.
- Boundary duplicates are safe because `TelemetryStore` deduplicates by telemetry event id.

Keepalive comments are sent on idle reads:

```text
: keepalive
```

Redis stream failures are sent as a typed SSE frame before the connection is closed:

```text
event: stream-error
data: {"message":"Redis stream unavailable"}
```

Redis Stream retention is controlled by `TELEMETRY_STREAM_MAXLEN` and uses approximate max length. If a client falls behind retention, it should rehydrate via HTTP and reconnect from the current cursor.

Production notes:

- Add auth before exposing SSE outside trusted environments.
- Configure proxies/load balancers to avoid buffering `text/event-stream`.
- CORS must include the frontend origin.
- Rate limits and connection limits are future hardening items.

## Dashboard Configuration API

Dashboard and widget definitions are persisted in PostgreSQL. Telemetry data still flows through the telemetry endpoints; dashboard CRUD only stores configuration.

Endpoints:

- `GET /api/v1/dashboards`
- `POST /api/v1/dashboards`
- `GET /api/v1/dashboards/{id}`
- `PATCH /api/v1/dashboards/{id}`
- `DELETE /api/v1/dashboards/{id}`
- `POST /api/v1/dashboards/{id}/widgets`
- `PATCH /api/v1/dashboards/{id}/widgets/{widgetId}`
- `DELETE /api/v1/dashboards/{id}/widgets/{widgetId}`

Widget JSON uses camelCase:

```json
{
  "title": "API latency",
  "type": "line",
  "metric": "latency",
  "service": "api-gateway",
  "region": "us-east",
  "aggregation": "avg",
  "bucket": "1m",
  "timeRange": "15m",
  "position": 0,
  "width": 2,
  "height": 1,
  "thresholdWarning": 150,
  "thresholdCritical": 250
}
```

Supported widget types are `line`, `bar`, `scatter`, `heatmap`, and `stat`. Supported metrics match the metrics query endpoint: `latency`, `throughput`, `cpuUsage`, `memoryUsage`, `errorRate`, and `payloadSize`.

## Alerting API

Alert rules are backend-owned and evaluated asynchronously by Celery. JSON uses camelCase. Celery scans for due rules every 5 seconds by default; rule evaluation intervals must be at least 5 seconds.

## Authentication And Workspaces

Configuration APIs require bearer access tokens. Refresh tokens are HttpOnly cookies and are never returned in JSON.

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET|POST /api/v1/workspaces`
- `GET|PATCH /api/v1/workspaces/{id}`
- `GET|POST /api/v1/workspaces/{id}/members`
- `PATCH|DELETE /api/v1/workspaces/{id}/members/{userId}`

Dashboard, widget, alert and incident requests use `X-Workspace-Id` to select the active workspace. Telemetry ingestion, telemetry query and telemetry SSE remain unscoped in Phase 7.

| Role | Read config | Edit dashboards | Edit alerts | Manage members |
| --- | --- | --- | --- | --- |
| owner | yes | yes | yes | yes |
| admin | yes | yes | yes | non-owner roles |
| member | yes | yes | yes | no |
| viewer | yes | no | no | no |

Endpoints:

- `GET /api/v1/alerts`
- `POST /api/v1/alerts`
- `GET /api/v1/alerts/{id}`
- `PATCH /api/v1/alerts/{id}`
- `DELETE /api/v1/alerts/{id}`
- `POST /api/v1/alerts/{id}/evaluate`
- `GET /api/v1/incidents`
- `GET /api/v1/incidents/{id}`

Alert rule shape:

```json
{
  "name": "High API latency",
  "metric": "latency",
  "service": "api-gateway",
  "region": "us-east",
  "aggregation": "avg",
  "bucket": "1m",
  "evaluationWindowSeconds": 300,
  "operator": ">=",
  "threshold": 200,
  "evaluationIntervalSeconds": 60,
  "cooldownSeconds": 300,
  "enabled": true
}
```

State machine:

- Alert rules expose `normal` or `firing`.
- Incidents expose `firing` or `resolved`.
- The evaluator opens one active incident for a rule when it transitions into firing.
- If a firing rule clears, the active incident is resolved.
- Cooldown prevents immediate reopen side effects after resolution; it does not hide an already-firing state.

Current limitations: telemetry events are not workspace-scoped yet, and there are no notifications, acknowledgements, escalation, incident assignment, OAuth, password reset or billing flows.
