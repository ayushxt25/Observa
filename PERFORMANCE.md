# PulseGrid Performance Notes

## Performance Goals

- Retain at least 10,000 telemetry points.
- Support 50,000 and 100,000 point capacity presets.
- Append simulated telemetry every 100ms without unbounded memory growth.
- Keep chart rendering responsive by drawing dense marks on Canvas.
- Keep React rerenders bounded and explainable.

## Test Environment

Fill this in on the machine used for final recruitment verification:

| Field | Value |
| --- | --- |
| Date | TODO |
| Browser and version | TODO |
| OS | TODO |
| CPU | TODO |
| RAM | TODO |
| DevTools open? | TODO |
| Build or dev mode | TODO |

## Bounded Memory Strategy

Telemetry lives in `TelemetryStore`, which owns a fixed-capacity circular buffer. New writes overwrite the oldest slot once capacity is reached. The implementation never uses repeated `Array.shift()` for retained telemetry, so appending remains stable as the dataset grows.

## Circular Buffer Strategy

`RingBuffer<T>` tracks a start index and logical length. Writes land at `(start + length) % capacity` until full; after that the write replaces `start` and advances it by one slot.

## Rendering Strategy

Charts use Canvas for dense visual marks and SVG for lightweight semantic overlays. Canvas rendering is scheduled only when inputs, size or interaction state changes. Each chart cleans up animation frames and ResizeObserver subscriptions.

## Canvas And SVG Integration

The latency chart uses Canvas for the line and SVG for axis lines, tick labels, title, description and crosshair. The scatter plot uses Canvas for dense points and SVG for axes, tick labels, title and description. This avoids thousands of SVG nodes while keeping chart structure inspectable and accessible.

## React Optimization Techniques

- Mutable high-frequency data is stored in an external telemetry store instead of React state.
- React state carries controls, summary values and version counters.
- UI notifications are batched independently from 100ms ingestion.
- Context values and callbacks are memoized.
- Chart components and the virtualized table use memoization where prop churn is expensive.
- `useTransition` is used for aggregation, service filtering, time-range and stress-mode changes.
- `useDeferredValue` is used for the reduced-cadence table snapshot.

## Next.js Optimizations

The dashboard page is a Server Component that generates the initial serializable dataset. The interactive dashboard is isolated behind a Client Component boundary. The generated data endpoint is an App Router Route Handler. The production build statically generates `/dashboard` when appropriate.

## Server Versus Client Decisions

- Server: initial 10,000-point dataset generation in `app/dashboard/page.tsx`.
- Client: replaceable telemetry source lifecycle, bounded store, Canvas, ResizeObserver, pointer interaction, Context provider, controls, worker lifecycle and performance APIs.
- Route Handler: `/api/data` returns configurable generated batches for demonstration and integration testing.

## Source, Store And Query Architecture

`SimulationTelemetrySource` emits deterministic telemetry batches through a `TelemetrySource` interface. `TelemetryStore` owns bounded retention and exposes lightweight immutable snapshots plus read/query methods. The telemetry query layer handles time ranges, service filtering, summaries, aggregation periods and heatmap input. `TelemetryWorkerClient` centralizes worker requests, response IDs, stale-response protection, fallback processing and termination.

`RemoteTelemetrySource` implements the same source contract for the FastAPI backend. It polls capped raw telemetry results, maps API DTOs into frontend telemetry events, cancels stale requests with `AbortController`, exposes connection status, and feeds `TelemetryStore` rather than bypassing it. Non-raw latency aggregation in remote mode can use the backend SQL metric query endpoint; charts still consume render-ready frontend data.

Remote mode now hydrates capped workspace history over HTTP and uses authenticated Server-Sent Events for incremental raw telemetry batches. The SSE endpoint reads workspace Redis Streams with blocking reads and keepalive comments; it does not poll PostgreSQL for live delivery.

Remote raw event queries are capped server-side and fallback polling uses timestamp watermarks. `TelemetryStore` deduplicates by event id before appending to the bounded ring buffer, so repeated boundary records do not grow retained client data.

Hydration race strategy:

1. Capture the current Redis Stream cursor.
2. Hydrate the latest bounded PostgreSQL window over HTTP.
3. Open SSE from that cursor.
4. Rely on store id deduplication for boundary replay safety.

## Aggregation And Downsampling

Aggregation modes are raw, 1 minute, 5 minutes and 1 hour. Aggregation computes average, minimum, maximum and count. The latency line uses viewport-aware min/max downsampling when source points substantially exceed horizontal pixels.

## Worker Strategy

`TelemetryWorkerClient` owns communication with `workers/data.worker.ts`, which handles aggregation and heatmap calculation when filters, time range, aggregation or stress settings change. It uses typed request and response messages, and stale responses are ignored using request ids. The client falls back to main-thread aggregation when Worker is unavailable.

In remote mode, backend SQL aggregation is used for non-raw latency series where appropriate. The worker still supports local derivations such as heatmap data from retained points.

## Configurable Dashboard Strategy

Phase 5 stores dashboard and widget configuration in PostgreSQL while keeping high-frequency telemetry in `TelemetryStore`. Dashboard config is low-frequency UI state and is isolated from the telemetry source lifecycle. All widgets share the same `RemoteTelemetrySource` and SSE connection for a dashboard session.

Widget rendering uses a central renderer boundary that maps widget config to existing chart inputs. Short live windows are derived from retained events in the external store. Historical telemetry and backend latency aggregation remain available through the HTTP API. A lightweight query-cache utility provides stable metric query keys and in-flight request deduplication for future backend-backed widget queries without creating a large client cache.

Thresholds are semantic frontend evaluation rules: `normal`, `warning`, or `critical`. Styling consumes those states.

## Alert Evaluation Strategy

Phase 6 alert rules are evaluated server-side by Celery. Beat schedules one periodic scan task every 5 seconds by default; rule evaluation intervals have a 5-second minimum and are respected by selecting only enabled rules whose interval has elapsed. The worker evaluates each selected rule through indexed PostgreSQL time-window metric queries. The evaluator does not scan the entire telemetry table: each rule uses service/region/time filters and the existing metric aggregation path.

State transitions and incident writes happen in one SQLAlchemy transaction. A partial PostgreSQL unique index prevents more than one active `firing` incident per rule, while service logic also checks the active incident before creating one. If evaluation fails, the transaction rolls back and the next scheduled scan can retry. Redis/Celery failure pauses alert evaluation but does not stop telemetry ingestion, historical HTTP queries, or SSE delivery.

Notification delivery is decoupled from alert evaluation. The evaluator writes pending delivery rows for attached channels and commits before enqueueing Celery tasks, so outbound email/webhook network latency is not part of the alert state-transition transaction. Delivery workers claim one row at a time, commit `delivering`, perform network I/O outside the claim transaction, then mark `delivered`, `pending`, or `failed`. Stale `delivering` rows are recovered after `NOTIFICATION_DELIVERY_LEASE_SECONDS`. The retry scanner uses indexed `workspace_id/status/next_retry_at` and `status/last_attempt_at` paths and avoids scanning delivered history.

Audit logging is intentionally low-volume. It records security-sensitive and product mutations, not high-frequency telemetry ingestion, telemetry reads, chart refreshes or automatic alert evaluation ticks. Audit reads use bounded newest-first pagination with workspace/action/actor/resource/outcome indexes.

The frontend alert panel polls rule and incident state at a modest interval. It does not evaluate alert conditions in the browser and does not create additional SSE connections.

## Service Catalog And Topology Strategy

Service catalog state is low-frequency workspace configuration. It is loaded through normal authenticated HTTP APIs and is not mixed into `TelemetryStore` or high-frequency React telemetry context. Telemetry ingestion auto-discovers services per accepted batch by grouping unique service names before writing catalog rows, avoiding one catalog query/write per telemetry row.

Service health summaries use indexed workspace/service/time telemetry filters over a recent five-minute window plus workspace-scoped alert/incident counts. The topology view is an SVG layer with a deterministic radial layout, pan/zoom state, hover, and click selection. It targets modest catalogs around 50 services smoothly and 100 services usefully; it does not add a graph-rendering dependency or create service-specific streams.

## Query Engine Cache Strategy

Historical dashboard queries use two cache layers. The browser `QueryCache` deduplicates in-flight requests and keeps results for 10 seconds. The backend Query Engine can then serve successful public historical queries from Redis for `QUERY_CACHE_TTL_SECONDS` with workspace-aware SHA-256 keys. Cache values are serialized JSON responses with TTLs and optional max-size skipping; Redis get/set/decode failures fall back to PostgreSQL.

Alert evaluation bypasses Redis Query Cache so new telemetry can change alert state immediately. Service health remains on the uncached grouped summary path in this phase because it already uses one efficient SQL query and combines telemetry with live alert/incident state.

## Auth And Tenancy Performance

Auth state is held in a low-frequency React context separate from telemetry storage and chart rendering. API requests attach an in-memory access token and active workspace id; concurrent `401` responses share one refresh request and retry once. Workspace switches reload dashboard and alert configuration but do not restart telemetry sources or chart pipelines.

Backend RBAC uses indexed membership lookups plus workspace foreign keys on dashboards, alert rules, incidents and telemetry. Telemetry read paths require the active workspace, while machine ingestion derives workspace identity from API keys.

## Live Streaming Strategy

Ingestion commits to PostgreSQL first, then publishes the accepted batch to Redis Stream `telemetry:events:{workspaceId}`. A Redis publish failure does not roll back durable ingestion. SSE clients read directly from the active workspace stream using blocking `XREAD`, avoiding unbounded per-client queues. Slow clients that fall behind Redis retention should perform HTTP rehydration and reconnect from the current cursor.

## Virtualization Strategy

The table uses a fixed row height. It computes visible start and end indexes from `scrollTop`, renders only visible rows plus overscan, and uses spacer elements to preserve scroll height. The UI displays rendered rows versus total rows.

## FPS Methodology

FPS is measured from `requestAnimationFrame` timestamps over rolling one-second windows. Frame duration is calculated from recent frame deltas and displayed in milliseconds.

## Interaction-Latency Methodology

Aggregation, service-filter, time-range and stress-mode interactions call `performance.mark` at user action start and `performance.measure` when the corresponding data-processing path completes. The latest measured interaction latency is displayed in milliseconds.

## Memory Methodology

Heap usage is displayed only when the browser exposes `performance.memory.usedJSHeapSize`. Unsupported browsers show `Not supported`. Heap values should be treated as approximate browser diagnostics, not precise application memory accounting.

## Benchmark Methodology

Measure on the target browser and hardware with DevTools closed and then open, using:

- 10,000 retained points at batch size 10.
- 50,000 retained points at batch size 50.
- 100,000 retained points at batch size 100.
- Stress mode at each capacity.
- Aggregation changes across raw, 1 minute, 5 minutes and 1 hour.
- Service filter and time-range changes.

## Browser JavaScript Asset Size Methodology

Run `npm run build` first, then run `npm run analyze:size`. The script recursively reads browser-delivered JavaScript assets from `.next/static/chunks`, counts only `.js` files, excludes source maps, sums raw bytes from the build output, and sums gzip-compressed bytes using Node's built-in `node:zlib` `gzipSync` per asset.

This is an aggregate build-asset measurement. It may include shared chunks that are not all loaded on the `/dashboard` route in a real browser session.

Measured on the current completed production build:

```text
PulseGrid browser JavaScript asset size
Directory: .next\static\chunks
Method: recursively sum .js files; source maps are excluded; gzip uses node:zlib gzipSync per asset.
Note: aggregate build-asset measurement; may include shared chunks not all loaded on the dashboard route.
JavaScript files counted: 13
Raw total bytes: 752320
Gzip total bytes: 221455
```

## Phase 14 Release-Candidate Measurements

Measured on the local Docker stack and Chromium smoke session during the v1.0.0 release-candidate pass.

| Area | Scenario | Result | Notes |
| --- | --- | --- | --- |
| Ingestion | 1,000 event batch | 0.150 s, about 6,665 events/s | API-key authenticated batch ingest into PostgreSQL plus Redis publish. |
| Ingestion | 10,000 event batch | 1.321 s, about 7,571 events/s | Same path; Redis and PostgreSQL healthy. |
| Query Engine | Fixed explicit query repeated | first `miss`, second `hit` | Redis cache key included workspace and normalized request fields. |
| Query Engine | p95 latency, 1h, service filter | about 11 ms HTTP cold sample | Measured through API on seeded local Docker data. |
| Query Engine | grouped p95 by service | about 62 ms HTTP cold sample | Measured through API on seeded local Docker data. |
| Alerts | 12 concurrent breached evaluations | one firing incident, one opened event | PostgreSQL row locking and partial unique index preserved. |
| Alerts | 12 concurrent clear evaluations | one resolved incident, one resolved event | No duplicate resolution transition. |
| Incident impact | Four-service chain | depth 3, four affected services | `source -> target` means source depends on target; impact walks reverse dependents. |
| Browser smoke | Dashboard + incident intelligence | passed desktop, tablet, mobile smoke | No new console errors observed after authenticated flow. |
| Failure handling | Redis stopped | `/ready` degraded, recovered after restart | Historical queries fall back to PostgreSQL when cache is unavailable. |
| Failure handling | PostgreSQL stopped | `/ready` degraded, recovered after restart | Expected dependency outage signal. |

## Legacy Browser Stress Table

Measured values must be filled in after running on the target machine. Do not infer or invent them.

| Scenario | Browser | Capacity | Batch size | FPS | Frame ms | Chart render ms | Data processing ms | Interaction latency ms | Heap | Long tasks | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Baseline | TBD | 10,000 | 10 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | Not yet measured |
| Stress | TBD | 100,000 | 100 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | Not yet measured |

## Bottleneck Analysis

Likely bottlenecks to watch during manual testing:

- Full snapshot copies when invoking worker aggregation.
- Scatter plot domain scans on very large visible ranges.
- Heatmap bucket creation during stress mode.
- Browser support differences for long-task and heap APIs.

## Scaling To 100,000 And 1,000,000 Points

100,000 points are handled by the existing ring buffer, worker aggregation, downsampling and table virtualization. For 1,000,000 points, use typed-array storage for numeric columns, keep categorical dictionaries, aggregate incrementally by bucket, and avoid copying full snapshots into workers.

## Handling 10ms Updates

At 10ms updates, generation should batch writes, aggregate incrementally and reduce UI notification cadence further. Charts should render from prepared views rather than filtering raw points on every tick.

## Limitations

- Worker requests currently receive snapshots rather than shared typed-array buffers.
- Heap reporting depends on non-standard browser APIs.
- Benchmark fields are intentionally placeholders until measured on the target machine.

## Browser Compatibility Notes

Modern Chromium, Firefox and Safari support the core Canvas, SVG and ResizeObserver path. Long-task counts depend on PerformanceObserver longtask support. Worker fallback covers environments without Web Worker support.

## Incident Intelligence

Incident impact queries avoid per-node database access. The backend loads the incident/alert root, the workspace service catalog, and the workspace dependency graph, then performs an in-memory breadth-first traversal over upstream dependents. This is intended to be trivial for 10-100 services and usable for several hundred services; dependency impact remains distinct from telemetry-derived service health.
