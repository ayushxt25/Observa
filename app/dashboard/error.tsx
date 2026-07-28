"use client";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <main className="dashboard-page">
      <section className="panel error-panel">
        <h1>PulseGrid could not load</h1>
        <p>{error.message}</p>
        <button type="button" onClick={reset}>Try again</button>
      </section>
    </main>
  );
}
