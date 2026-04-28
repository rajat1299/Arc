import Link from "next/link";

import type { RunRow } from "./data";
import { formatCostUSD, formatDurationMs, formatTokens } from "./format";
import { StatusDot } from "./StatusDot";
import { runHref } from "./urls";

type Props = {
  runs: RunRow[];
  selectedRunId: string | null;
};

export function RunTable({ runs, selectedRunId }: Props) {
  if (runs.length === 0) {
    return <RunTableEmpty />;
  }

  return (
    <div className="run-list" role="list" aria-label="Recent runs">
      {runs.map((run) => (
        <RunRowItem key={run.id} run={run} selected={run.id === selectedRunId} />
      ))}
    </div>
  );
}

function RunRowItem({ run, selected }: { run: RunRow; selected: boolean }) {
  const accentClass =
    run.status === "failed"
      ? "is-failed"
      : run.status === "suboptimal"
        ? "is-suboptimal"
        : run.status === "running"
          ? "is-running"
          : "";

  return (
    <Link
      role="listitem"
      className={`run-card ${selected ? "is-selected" : ""} ${accentClass}`.trim()}
      href={runHref(run.id)}
      aria-current={selected ? "page" : undefined}
      aria-label={`Open run ${run.workflow} ${run.id}`}
    >
      <div className="run-card-heading">
        <span className={`status-label s-${run.status}`}>
          <StatusDot status={run.status} decorative />
          {run.status}
        </span>
        <span className="run-started">{run.startedRelative}</span>
      </div>
      <div className="run-card-title">
        <span className="run-workflow">{run.workflow}</span>
        <span className="run-id">{run.id}</span>
      </div>
      <div className="run-card-meta">
        <span>{run.runtime}</span>
        <span>{run.environment ?? "default"}</span>
        <span>{run.tenant}</span>
      </div>
      <div className="run-card-stats">
        <span>
          <strong>{formatDurationMs(run.durationMs)}</strong>
          <small>Duration</small>
        </span>
        <span>
          <strong>{formatCostUSD(run.costUsd)}</strong>
          <small>Cost</small>
        </span>
        <span>
          <strong>{formatTokens(run.totalTokens)}</strong>
          <small>Tokens</small>
        </span>
        <span>
          <strong>{run.spanCount}</strong>
          <small>{run.eventCount} ev</small>
        </span>
      </div>
    </Link>
  );
}

function RunTableEmpty() {
  return (
    <div className="empty">
      <strong>No runs yet</strong>
      Start an agent and its trace will appear here.
    </div>
  );
}
