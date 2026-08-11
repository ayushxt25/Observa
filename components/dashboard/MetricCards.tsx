"use client";

import { useTelemetryQuery } from "@/hooks/useTelemetryQuery";

const integerFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

export function MetricCards() {
  const { summary } = useTelemetryQuery();

  const cards = [
    {
      label: "Retained points",
      value: integerFormatter.format(summary.totalPoints),
    },
    {
      label: "Throughput",
      value: `${integerFormatter.format(summary.totalThroughput)} rps`,
    },
    {
      label: "Avg latency",
      value: `${summary.avgLatency.toFixed(1)} ms`,
    },
    {
      label: "Error rate",
      value: `${summary.avgErrorRate.toFixed(2)}%`,
    },
  ];

  return (
    <section className="metric-grid">
      {cards.map((card) => (
        <article className="metric-card" key={card.label}>
          <span>{card.label}</span>
          <strong>{card.value}</strong>
        </article>
      ))}
    </section>
  );
}
