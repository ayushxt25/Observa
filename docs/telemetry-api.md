# Observa Telemetry API Contract

This document describes the Observa backend telemetry contract used by remote dashboard mode.

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

The `id` field is the client-supplied telemetry event identifier. It is unique per workspace, not globally unique. PostgreSQL uses an internal `db_id` primary key and enforces `UNIQUE(workspace_id, id)` so different workspaces may ingest the same external event id without conflict. Re-ingesting the same event id in the same workspace is idempotent and counts as zero newly accepted rows.

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

`POST /api/v1/query`

Runs the reusable workspace-scoped Query Engine used by historical dashboard widgets. Requests are authenticated with the active workspace context; clients cannot submit `workspaceId`.

Successful public query responses may be cached in Redis for a short TTL. Cache keys include workspace id, metric, aggregation, bucket, groupBy, scalar filters, normalized UTC start/end, limit and server safety limits. Redis cache failures are treated as misses and PostgreSQL remains the source of truth. Response metadata may include `cacheStatus` as `hit`, `miss`, or `bypass`.

Alert evaluation bypasses this cache so incident transitions use fresh PostgreSQL telemetry. Service health uses its existing grouped summary path and remains uncached in this phase.

`GET /api/v1/metrics/query`

Compatibility endpoint for older metric-query consumers. Current migrated dashboard historical Line/Stat/Bar widgets use `POST /api/v1/query`; this endpoint remains available for compatibility and is not deleted in Phase 12F.

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

Used by `RemoteTelemetrySource` to hydrate and incrementally refresh the frontend `TelemetryStore`. In Phase 8 this endpoint requires user JWT auth plus validated `X-Workspace-Id`.

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
- SSE `id:` is the Redis Stream cursor, distinct from each telemetry event payload `id`.
- Boundary duplicates are safe because `TelemetryStore` deduplicates by telemetry event id within the active workspace lifecycle; workspace switches clear the store and reset the cursor.

Keepalive comments are sent on idle reads:

```text
: keepalive
```

Redis stream failures are sent as a typed SSE frame before the connection is closed:

```text
event: stream-error
data: {"message":"Redis stream unavailable"}
```

Redis Stream retention is controlled by `TELEMETRY_STREAM_MAXLEN` per workspace stream and uses approximate max length. If a client falls behind retention, it should rehydrate via HTTP and reconnect from the current cursor.

Production notes:

- SSE uses fetch-based clients with bearer access-token and `X-Workspace-Id` headers. Membership is revalidated periodically while streaming.
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

Dashboard, widget, alert, incident and telemetry read requests use `X-Workspace-Id` to select the active workspace. Telemetry ingestion uses workspace API keys; clients cannot submit `workspaceId` in telemetry payloads.

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

## Notification Channels And Deliveries

Notification channels are workspace-scoped and reusable across alert rules.

Endpoints:

- `GET|POST /api/v1/notification-channels`
- `GET|PATCH|DELETE /api/v1/notification-channels/{id}`
- `POST /api/v1/notification-channels/{id}/test`
- `PUT /api/v1/alerts/{id}/notification-channels`
- `GET /api/v1/notification-deliveries`
- `GET /api/v1/notification-deliveries/{id}`

Supported channel types are `email` and `webhook`. Webhook responses redact secrets and expose only `hasSecret`. Email channels store validated recipients. Webhook channels store `targetUrl`, optional label, and an encrypted signing secret.

Webhook payloads include:

```json
{
  "schemaVersion": "2026-08-09",
  "deliveryId": "delivery-id",
  "eventType": "firing",
  "workspaceId": "workspace-id",
  "alertRuleId": "alert-id",
  "alertName": "High latency",
  "incidentId": "incident-id",
  "incidentStatus": "firing",
  "metric": "latency",
  "triggeringValue": 250.5,
  "threshold": 200,
  "operator": ">=",
  "service": "api-gateway",
  "region": "us-east",
  "openedAt": "2026-08-09T00:00:00Z",
  "resolvedAt": null,
  "timestamp": "2026-08-09T00:00:01Z"
}
```

If a webhook secret is configured, the raw request body is signed with HMAC-SHA256 using:

```text
X-Observa-Timestamp: <unix-seconds>
X-Observa-Delivery-Id: <notification-delivery-id>
X-Observa-Signature: sha256=<hex-hmac(timestamp + "." + raw-body)>
```

Delivery states are `pending`, `delivering`, `delivered`, and `failed`. Retryable webhook failures are network/timeouts, HTTP `408`, `429`, and `5xx`; most `4xx` responses are terminal. Retries use bounded exponential backoff and are scanned by Celery. Delivery idempotency is enforced by `(incidentId, channelId, eventType)`.

Delivery semantics are at-least-once. If a worker crashes after a receiver accepts a webhook but before Observa marks the row delivered, Observa may retry. Consumers should deduplicate using `deliveryId` or `X-Observa-Delivery-Id`. Email receivers may receive duplicates in the same crash window.

Delivery rows snapshot the channel name, type, config and encrypted webhook secret when the alert transition happens. Later channel edits or deletion do not change already-created delivery behavior. A stale `delivering` row is recovered by the retry scanner after `NOTIFICATION_DELIVERY_LEASE_SECONDS`.

## Service Catalog

`GET /api/v1/services` remains the telemetry-observed service discovery endpoint.

The persisted Service Catalog uses separate workspace-scoped endpoints:

- `GET /api/v1/services/catalog`
- `POST /api/v1/services/catalog`
- `GET /api/v1/services/catalog/{id}`
- `PATCH /api/v1/services/catalog/{id}`
- `DELETE /api/v1/services/catalog/{id}`
- `GET /api/v1/services/catalog/{id}/summary`
- `GET /api/v1/service-dependencies`
- `POST /api/v1/service-dependencies`
- `PATCH /api/v1/service-dependencies/{id}`
- `DELETE /api/v1/service-dependencies/{id}`

Catalog rows are auto-created from accepted telemetry ingestion batches. The canonical `name` corresponds to the telemetry event `service` field and is immutable through PATCH so historical telemetry remains attached. Editable metadata includes `displayName`, `description`, `environment`, `version`, `ownerTeam`, `repositoryUrl`, `runbookUrl`, and `tags`.

Service summaries derive health from the active workspace only:

- `unknown`: no recent telemetry and no active service alert/incident.
- `critical`: active incident, average recent error rate >= 5%, or average recent latency >= 500 ms.
- `degraded`: active firing alert, average recent error rate >= 1%, or average recent latency >= 250 ms.
- `healthy`: recent telemetry with none of the degraded/critical conditions.

Service dependencies are manually configured relationships between catalog rows. Supported dependency types are `http`, `queue`, `database`, and `unknown`. The backend rejects self-dependencies, duplicate edges, and cross-workspace service ids. No distributed tracing inference exists yet.

## Audit Events

Audit events are generated server-side for workspace mutations and security-sensitive auth outcomes. There are no create, patch, or delete endpoints for normal users.

Endpoints:

- `GET /api/v1/audit-events`
- `GET /api/v1/audit-events/{id}`

Reads require owner/admin role in the active workspace. List filters include `actorUserId`, `actorType`, `action`, `resourceType`, `resourceId`, `outcome`, `start`, `end`, `cursor`, and `limit`. Results are newest-first, cursor-paginated, and capped at 200 rows per page.

Audit metadata is recursively redacted before persistence. Passwords, password hashes, access tokens, refresh tokens, API keys, key hashes, webhook secrets, encrypted secret values, SMTP credentials, cookies, and authorization headers must not appear in stored metadata. Product mutation audit rows are mandatory and share the domain mutation transaction. Auth outcome audit rows are best-effort within the available workspace context; unknown-email login failures are not persisted because there is no workspace scope. Client IP currently comes from `request.client.host`; proxy-derived IP support requires explicit trusted-proxy configuration later. Audit logs are append-oriented application records, not a cryptographically immutable ledger; PostgreSQL administrators can still alter records.

Current limitations: there are no Slack/PagerDuty integrations, acknowledgements, escalation, incident assignment, OAuth, password reset or billing flows.

## Incident Intelligence

Incident intelligence is workspace-scoped and read-only for all roles that can read incidents.

Endpoints:

- `GET /api/v1/incidents/{id}/timeline`
- `GET /api/v1/incidents/{id}/impact`
- `GET /api/v1/incidents/{id}/notifications/summary`

The timeline contains low-noise incident lifecycle events plus notification delivery milestones. It does not include every alert evaluation tick, telemetry batch, SSE read, or notification retry attempt.

Service dependency direction is `source -> target`, meaning the source service depends on the target service. For an incident rooted at `target`, blast radius walks upstream dependents transitively. Cycles are handled with a visited set, and services reachable through multiple paths are returned once with minimum depth. If an incident has no service-specific alert or the catalog row has been deleted, impact returns an unavailable reason instead of failing.

Impact status is not observed health. A service can be `affected` by a downstream/root dependency while its own telemetry-derived health remains `healthy`.
