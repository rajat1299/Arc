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
    <table className="run-table" aria-label="Recent runs">
      <thead>
        <tr>
          <th scope="col" className="col-status">
            Status
          </th>
          <th scope="col" className="col-workflow">
            Workflow
          </th>
          <th scope="col" className="col-runtime">
            Runtime
          </th>
          <th scope="col" className="col-tenant">
            Tenant
          </th>
          <th scope="col" className="col-spans num">
            Spans
          </th>
          <th scope="col" className="col-duration num">
            Duration
          </th>
          <th scope="col" className="col-cost num">
            Cost
          </th>
          <th scope="col" className="col-tokens num">
            Tokens
          </th>
          <th scope="col" className="col-started num">
            Started
          </th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => (
          <RunRowItem key={run.id} run={run} selected={run.id === selectedRunId} />
        ))}
      </tbody>
    </table>
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
    <tr
      className={`${selected ? "is-selected" : ""} ${accentClass}`.trim()}
      aria-selected={selected}
    >
      <td className="col-status">
        <span className={`status-label s-${run.status}`}>
          <StatusDot status={run.status} />
          {run.status}
        </span>
      </td>
      <td className="col-workflow">
        <Link
          className="run-cell-link"
          href={runHref(run.id)}
          aria-current={selected ? "page" : undefined}
          aria-label={`Open run ${run.workflow} ${run.id}`}
        >
          <div className="cell-stack">
            <span className="run-workflow">{run.workflow}</span>
            <span className="run-id">{run.id}</span>
          </div>
        </Link>
      </td>
      <td className="col-runtime">
        <span className="run-runtime">{run.runtime}</span>
      </td>
      <td className="col-tenant">
        <span className="cell-mono">{run.tenant}</span>
      </td>
      <td className="col-spans num">
        {run.spanCount}
        <span className="run-id"> · {run.eventCount} ev</span>
      </td>
      <td className="col-duration num">{formatDurationMs(run.durationMs)}</td>
      <td className="col-cost num">{formatCostUSD(run.costUsd)}</td>
      <td className="col-tokens num">{formatTokens(run.totalTokens)}</td>
      <td className="col-started num">{run.startedRelative}</td>
    </tr>
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
