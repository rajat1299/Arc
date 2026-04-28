import type { MetricsSummary } from "./data";
import { formatCostUSD, formatDurationMs, formatTokens } from "./format";

type Props = {
  metrics: MetricsSummary | null;
};

export function SummaryStrip({ metrics }: Props) {
  const cells = buildCells(metrics);
  return (
    <section className="summary" aria-label="Run metrics, last 24 hours">
      {cells.map((cell) => (
        <Cell key={cell.label} {...cell} />
      ))}
    </section>
  );
}

type CellProps = {
  label: string;
  value: string;
  sub?: string;
  muted?: boolean;
  tone?: "accent" | "danger" | "warning" | "success";
};

function Cell({ label, value, sub, muted, tone }: CellProps) {
  return (
    <div className={`summary-cell${muted ? " is-muted" : ""}`}>
      <span className="summary-label">{label}</span>
      <span className={`summary-value${tone ? ` tone-${tone}` : ""}`}>{value}</span>
      {sub !== undefined ? <span className="summary-sub">{sub}</span> : null}
    </div>
  );
}

function buildCells(metrics: MetricsSummary | null): CellProps[] {
  if (metrics === null) {
    return [
      { label: "Total runs", value: "—", muted: true },
      { label: "Failed", value: "—", muted: true },
      { label: "Suboptimal", value: "—", muted: true },
      { label: "Total cost", value: "—", muted: true },
      { label: "Total tokens", value: "—", muted: true },
      { label: "p95 latency", value: "—", muted: true },
    ];
  }

  return [
    {
      label: "Total runs",
      value: metrics.totalRuns.toLocaleString("en-US"),
      sub: metrics.runningRuns > 0 ? `${metrics.runningRuns} running` : undefined,
      tone: metrics.runningRuns > 0 ? "accent" : undefined,
    },
    {
      label: "Failed",
      value: metrics.failedRuns.toLocaleString("en-US"),
      muted: metrics.failedRuns === 0,
      tone: metrics.failedRuns > 0 ? "danger" : undefined,
    },
    {
      label: "Suboptimal",
      value: metrics.suboptimalRuns.toLocaleString("en-US"),
      muted: metrics.suboptimalRuns === 0,
      tone: metrics.suboptimalRuns > 0 ? "warning" : undefined,
    },
    {
      label: "Total cost",
      value: formatCostUSD(metrics.totalCostUsd),
    },
    {
      label: "Total tokens",
      value: formatTokens(metrics.totalTokens),
    },
    {
      label: "p95 latency",
      value: formatDurationMs(metrics.p95LatencyMs),
      muted: metrics.p95LatencyMs === null,
    },
  ];
}
