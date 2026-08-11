# Changelog

## v1.0.0 - Release Candidate

Observa v1.0.0 is the first complete portfolio release.

- Workspace-scoped authentication, RBAC, dashboards, alerts, incidents, telemetry, services, audit logs, and notifications.
- API-key telemetry ingestion with hashed keys, tenant-aware PostgreSQL persistence, and workspace Redis Streams.
- Reusable PostgreSQL Query Engine with Redis query cache for historical dashboard analytics.
- Configurable dashboards using live TelemetryStore/SSE for realtime views and Query Engine for historical Line/Stat/Bar widgets.
- Alert evaluation through Celery with row-level concurrency protection, durable incidents, notification deliveries, retries, and incident intelligence.
- Service Catalog with manual dependency topology, health summaries, and blast-radius impact traversal.
- Security hardening for refresh sessions, cookie/CORS production config, webhook SSRF checks, secret redaction, and audit logging.

Known limitations for v1:

- Dependency topology is manually configured; there is no distributed tracing or OpenTelemetry collector.
- Notification delivery is at-least-once; webhook consumers should deduplicate by `deliveryId`.
- The legacy `GET /api/v1/metrics/query` endpoint remains as deprecated compatibility API.
- Backend Redis query cache has no distributed stampede lock.
