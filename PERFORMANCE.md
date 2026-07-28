# PulseGrid Performance Notes

## Goals

- Retain at least 10,000 telemetry points.
- Support 50,000 and 100,000 point capacity presets.
- Append simulated telemetry every 100ms without unbounded memory growth.
- Keep chart rendering responsive by drawing dense marks on Canvas.
- Keep React rerenders bounded and explainable.

## Bounded Memory Strategy

Telemetry lives in a fixed-capacity circular buffer. New writes overwrite the oldest slot once capacity is reached. The implementation never uses repeated `Array.shift()`, so appending remains stable as the dataset grows.

## Circular Buffer Strategy

`RingBuffer<T>` tracks a start index and logical length. Writes land at `(start + length) % capacity` until full; after that the write replaces `start` and advances it by one slot.

## Rendering Strategy

Charts use Canvas for dense visual marks and HTML for titles, labels, tooltips, legends and controls. Canvas rendering is scheduled only when inputs, size or interaction state changes. Each chart cleans up animation frames and ResizeObserver subscriptions.

## React Optimization Techniques

- Mutable high-frequency data is stored in refs.
- React state carries controls, summary values and version counters.
- UI notifications are batched.
- Context values are memoized.
- The raw table updates at a reduced cadence.

## Next.js Optimizations

The dashboard page is a Server Component that generates the initial serializable dataset. The interactive dashboard is isolated behind a Client Component boundary.

## Aggregation And Downsampling

Aggregation modes are raw, 1 minute, 5 minutes and 1 hour. Aggregation computes average, minimum, maximum and count. The latency line uses viewport-aware min/max downsampling when source points substantially exceed horizontal pixels.

## Worker Usage

`workers/data.worker.ts` handles aggregation and heatmap calculation when filters, time range, aggregation or stress settings change. It uses typed request and response messages and stale responses are ignored using request ids. The provider falls back to main-thread aggregation when Worker is unavailable.

## Virtualization Strategy

The table uses a fixed row height. It computes visible start and end indexes from `scrollTop`, renders only visible rows plus overscan, and uses spacer elements to preserve scroll height.

## Benchmark Methodology

Measure on the target browser and hardware with DevTools closed and then open, using:

- 10,000 retained points at batch size 10.
- 50,000 retained points at batch size 50.
- 100,000 retained points at batch size 100.
- Stress mode at each capacity.

## Results

Measured values must be filled in after running on the target machine.

| Scenario | Browser | Capacity | Batch size | FPS | Heap | Long tasks | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Baseline | TBD | 10,000 | 10 | TBD | TBD | TBD | Not yet measured |
| Stress | TBD | 100,000 | 100 | TBD | TBD | TBD | Not yet measured |

## Scaling To 100,000 And 1,000,000 Points

100,000 points are handled by the existing ring buffer, worker aggregation, downsampling and table virtualization. For 1,000,000 points, use typed-array storage for numeric columns, keep categorical dictionaries, aggregate incrementally by bucket, and avoid copying full snapshots into workers.

## Handling 10ms Updates

At 10ms updates, generation should batch writes, aggregate incrementally and reduce UI notification cadence further. Charts should render from prepared views rather than filtering raw points on every tick.

## `performance.memory` Limitations

`performance.memory` is non-standard and browser-specific. PulseGrid displays `Not supported` when unavailable and does not use it for control logic.

## Browser Compatibility Notes

Modern Chromium, Firefox and Safari support the core Canvas and ResizeObserver path. Long-task counts depend on PerformanceObserver longtask support. Worker fallback covers environments without Web Worker support.
