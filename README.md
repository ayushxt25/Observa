# PulseGrid

PulseGrid is a production-build-safe Next.js App Router telemetry dashboard MVP for monitoring distributed application services. It simulates realistic service telemetry, keeps retained data bounded, and renders dense charts manually with Canvas.

## Features

- Deterministic telemetry generation for latency, throughput, CPU, memory, error rate, payload size and status.
- Fixed-capacity ring buffer with 10,000, 50,000 and 100,000 point presets.
- Live updates every 100ms with pause, resume, reset, service filters, time ranges and stress mode.
- Canvas charts for latency, throughput, scatter density and service heatmap.
- HTML overlays for labels, tooltips, legends and interaction controls.
- Worker-backed aggregation with main-thread fallback.
- Custom virtualized raw telemetry table.
- Visible FPS, heap availability, long-task and retained-point monitoring.

## Architecture

The `/dashboard` page is a Server Component. It creates a serializable 10,000-point initial dataset and passes it to `DashboardClient`. Client state is provided through React Context and hooks only. The high-frequency store is a ref-backed `RingBuffer`, while React state carries only lightweight controls, summaries and version ticks.

Canvas handles dense marks because it can draw thousands of points without creating thousands of DOM nodes. HTML handles axes, labels, tooltips and controls because those are easier to make accessible and responsive outside the bitmap layer.

## Setup

```bash
npm install
npm run dev
```

Open `http://localhost:3000/dashboard`.

## Production Build

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```

## Performance Testing

Use the dashboard's Performance panel while changing capacity, batch size, aggregation and service filters. Stress mode fills the selected capacity immediately to exercise aggregation, charts and virtualization.

Do not record benchmark values in documentation until measured on the target machine and browser.

## Browser Compatibility

PulseGrid uses Canvas, ResizeObserver, Web Workers, requestAnimationFrame and PerformanceObserver. Heap usage is shown only in browsers that expose `performance.memory`; otherwise the UI reports `Not supported`.

## Server And Client Decisions

- `app/dashboard/page.tsx` remains a Server Component and generates initial data.
- `DashboardClient` and descendants are Client Components because they use hooks, timers, pointer events, Canvas and browser performance APIs.
- `app/api/data/route.ts` provides configurable generated batches for API-based validation or future polling.

## Project Structure

- `app/dashboard/*`: dashboard route, loading and error states.
- `app/api/data/route.ts`: generated telemetry batch API.
- `lib/*`: typed telemetry, generation, ring buffer, aggregation, downsampling and virtualization helpers.
- `components/providers/*`: ref-backed stream provider.
- `components/charts/*`: manual Canvas charts.
- `components/dashboard/*`: dashboard shell and KPI cards.
- `components/controls/*`: filters and range controls.
- `components/ui/*`: performance monitor and virtualized table.
- `workers/data.worker.ts`: worker aggregation path.
- `tests/*`: pure utility tests.

## Screenshots

Place screenshots in:

- `public/screenshots/dashboard-desktop.png`
- `public/screenshots/dashboard-mobile.png`
- `public/screenshots/stress-mode.png`

## Deployment

Build with `npm run build` and deploy as a standard Next.js application on Vercel or any host that supports Next.js App Router.
