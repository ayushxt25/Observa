# PulseGrid

High-performance real-time telemetry dashboard built with Next.js App Router, TypeScript, custom Canvas rendering, SVG overlays, custom table virtualization, bounded in-memory storage, and worker-backed processing.

[Live Demo](https://performance-dashboard-rose.vercel.app/dashboard)  
[GitHub Repository](https://github.com/ayushxt25/Performance-Dashboard)

`Next.js 16` `React 19` `TypeScript` `Canvas` `SVG overlays` `Web Worker` `Vitest`

## Project Preview

![PulseGrid dashboard overview](public/screenshots/dashboard-overview.png)

Dashboard overview captured from the deployed application. It shows the live telemetry header, KPI cards, stream controls, performance monitor, Canvas charts, heatmap, and virtualized table.

![PulseGrid stress test mode](public/screenshots/stress-test.png)

Stress-test mode using the real UI and live measured values. The screenshot is not edited and does not fabricate performance numbers.

![PulseGrid mobile dashboard](public/screenshots/mobile-dashboard.png)

Mobile viewport showing the responsive control panel and chart layout.

![PulseGrid virtualized table](public/screenshots/virtualized-table.png)

Raw telemetry table with custom virtual scrolling and rendered-row count.

## Overview

PulseGrid is a dark observability-style dashboard for monitoring simulated distributed application services. It generates telemetry for service latency, throughput, CPU usage, memory usage, error rate, payload size, region, and status.

The project is intentionally performance-focused. It retains large datasets in bounded memory, ingests new telemetry every 100ms, avoids external chart libraries, and renders dense chart marks manually with Canvas. Lightweight SVG and HTML layers handle axes, labels, descriptions, controls, and interaction affordances where DOM-based rendering is more appropriate.

PulseGrid was built as a recruitment assignment to demonstrate practical frontend architecture: Server Components for initial data, Client Components for interaction, careful React state boundaries, custom chart rendering, Web Worker processing, and production-build validation.

## Key Features

- Real-time simulated telemetry updates every 100ms.
- Typed telemetry model with services, regions, statuses, latency, throughput, CPU, memory, error rate, and payload size.
- Capacity presets for 10,000, 50,000, and 100,000 retained points.
- Fixed-capacity circular buffer to prevent unbounded memory growth.
- Pause, resume, reset, batch-size controls, and stress-test mode.
- Service filtering and time-range selection.
- Raw, 1-minute, 5-minute, and 1-hour aggregation modes.
- Canvas line chart for latency over time with zoom, pan, reset view, hover tooltip, and viewport-aware downsampling.
- Canvas bar chart for throughput by service.
- Canvas scatter plot for payload size versus latency.
- Service latency heatmap.
- SVG overlays for semantic chart structure, axis lines, tick labels, and the latency crosshair.
- Custom virtualized telemetry table without an external virtualization library.
- Visible performance monitor for FPS, frame duration, chart render duration, data-processing duration, interaction latency, retained/generated points, long tasks, and heap support detection.
- Web Worker aggregation path with stale-response protection and main-thread fallback.
- Responsive desktop, tablet, and mobile layout.
- App Router loading and error boundaries.
- Bundle-size analysis script for aggregate browser JavaScript assets.
- Focused Vitest coverage for the ring buffer, aggregation, downsampling, virtualization range calculation, and time-range filtering.

## Performance Highlights

- **Bounded retention:** telemetry is stored in a fixed-capacity ring buffer rather than an ever-growing array.
- **Decoupled ingestion and rendering:** new telemetry is generated every 100ms, while React receives batched lightweight updates instead of replacing the full retained dataset every tick.
- **Canvas for dense marks:** line, bar, and scatter chart marks are drawn to Canvas to avoid thousands of DOM nodes.
- **SVG and HTML overlays:** SVG provides semantic chart titles/descriptions, axes, tick labels, and crosshair elements; HTML handles controls, legends, and tooltips.
- **Viewport-aware downsampling:** the latency line reduces rendered points when source data substantially exceeds available horizontal pixels.
- **Worker-backed processing:** aggregation and heatmap calculation can run in a Web Worker, with request IDs used to ignore stale responses.
- **Custom virtualization:** the raw telemetry table renders only visible rows plus overscan and displays rendered rows versus total rows.
- **Measured bundle asset size:** `npm run analyze:size` reported `670,505` raw bytes and `200,902` gzip bytes across aggregate `.next/static/chunks` JavaScript assets for the completed production build.

The bundle-size result is an aggregate build-asset measurement. It may include shared chunks that are not all loaded on the dashboard route. Runtime performance varies by device, browser, build, and active controls. See [PERFORMANCE.md](PERFORMANCE.md) for methodology, caveats, and scaling notes.

## Architecture

```mermaid
flowchart TD
  A["Next.js Server Component<br/>app/dashboard/page.tsx"] --> B["Serializable initial telemetry<br/>10,000 points"]
  B --> C["Client DataProvider<br/>React Context + hooks"]
  C --> D["Bounded RingBuffer"]
  D --> E["Web Worker aggregation<br/>with stale response IDs"]
  D --> F["Canvas chart renderers"]
  F --> G["SVG/HTML overlays<br/>axes, labels, tooltips"]
  D --> H["Custom virtualized table"]
  I["Controls<br/>filter, range, capacity, stress"] --> C
  C --> J["Performance monitor<br/>FPS, memory support, timings"]
```

### Data Flow

1. `app/dashboard/page.tsx` generates the initial dataset as a Server Component.
2. `DashboardClient` passes that data into `DataProvider`.
3. `DataProvider` stores high-frequency telemetry in a ref-backed `RingBuffer`.
4. React state tracks controls, summary metrics, visible snapshots, and version counters.
5. Worker-backed processing recomputes aggregation and heatmap data when filters, ranges, aggregation, or stress mode changes.
6. Chart components render dense marks on Canvas and use SVG/HTML for lightweight overlays.
7. The telemetry table computes a visible range from `scrollTop` and renders only rows in that range plus overscan.

## Tech Stack

- Next.js App Router
- React
- TypeScript
- Canvas 2D API
- SVG overlays
- Web Workers
- ResizeObserver
- PerformanceObserver
- Vitest
- ESLint

No charting library, component library, external state-management library, database, authentication layer, WebSocket server, or middleware is used.

## Next.js Implementation

- `/dashboard` is implemented with the App Router.
- `app/dashboard/page.tsx` remains a Server Component for initial telemetry generation.
- Interactive dashboard functionality is isolated in Client Components.
- `/api/data` is an App Router Route Handler for generated telemetry batches.
- `loading.tsx` and `error.tsx` provide route-level loading and error states.
- The production build statically generates `/dashboard` and serves `/api/data` dynamically.

## Project Structure

```text
app/
  api/data/route.ts          Generated telemetry Route Handler
  dashboard/                 App Router dashboard route
components/
  charts/                    Manual Canvas charts and SVG overlays
  controls/                  Stream controls and time-range selector
  dashboard/                 Dashboard shell, header, KPI cards
  providers/                 Ref-backed DataProvider
  ui/                        Performance monitor and virtualized table
hooks/
  useDataStream.ts           Typed data Context hook
lib/
  aggregation.ts             Filtering, aggregation, heatmap helpers
  canvasUtils.ts             Canvas setup and downsampling helpers
  dataGenerator.ts           Deterministic telemetry generator
  performanceUtils.ts        Virtualization range calculation
  ringBuffer.ts              Fixed-capacity circular buffer
  types.ts                   Shared TypeScript types
workers/
  data.worker.ts             Worker aggregation path
tests/
  *.test.ts                  Focused Vitest tests for pure behavior
scripts/
  analyze-size.mjs           Aggregate JavaScript asset-size analyzer
public/screenshots/
  *.png                      README screenshots captured from deployment
```

## Getting Started

```bash
npm install
npm run dev
```

Open `http://localhost:3000/dashboard`.

## Available Scripts

```bash
npm run dev
npm run lint
npm run typecheck
npm run test
npm run build
npm run start
npm run analyze:size
```

`analyze:size` expects a completed production build and reads JavaScript assets from `.next/static/chunks`.

## Validation

The project is validated with:

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

The test suite covers:

- Circular-buffer overwrite behavior.
- Aggregation correctness and aggregation shape changes.
- Time-range filtering.
- Viewport-aware downsampling.
- Virtualized table range calculation.

## Deployment

The live deployment is available at:

https://performance-dashboard-rose.vercel.app/dashboard

The app can be deployed as a standard Next.js application on Vercel or any host that supports the Next.js App Router production build.

## Browser Notes

PulseGrid uses Canvas, SVG, ResizeObserver, Web Workers, requestAnimationFrame, and PerformanceObserver. Heap usage is shown only when the browser exposes `performance.memory`; otherwise the dashboard reports `Not supported`.

## Limitations

- The telemetry is simulated and deterministic; it is not connected to a production service or database.
- Worker requests currently receive snapshots rather than shared typed-array buffers.
- Benchmark values other than the aggregate JavaScript asset-size measurement are intentionally left as measurement placeholders in `PERFORMANCE.md`.
- Browser support for heap and long-task reporting varies.

## Documentation

- [PERFORMANCE.md](PERFORMANCE.md) explains rendering decisions, bounded memory, worker usage, virtualization, measurement methodology, and scaling considerations.
