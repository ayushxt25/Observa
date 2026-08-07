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

This structure keeps the chart layer independent of the current simulator so a future `RemoteTelemetrySource` can supply REST, SSE or WebSocket data without rewriting chart components.

## Aggregation And Downsampling

Aggregation modes are raw, 1 minute, 5 minutes and 1 hour. Aggregation computes average, minimum, maximum and count. The latency line uses viewport-aware min/max downsampling when source points substantially exceed horizontal pixels.

## Worker Strategy

`TelemetryWorkerClient` owns communication with `workers/data.worker.ts`, which handles aggregation and heatmap calculation when filters, time range, aggregation or stress settings change. It uses typed request and response messages, and stale responses are ignored using request ids. The client falls back to main-thread aggregation when Worker is unavailable.

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
JavaScript files counted: 12
Raw total bytes: 675006
Gzip total bytes: 202121
```

## Measured Results

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
