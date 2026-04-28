import Link from "next/link";

import type { RunRow, SpanNode } from "./data";
import { formatCostUSD, formatDurationMs } from "./format";
import { StatusDot } from "./StatusDot";
import { spanHref } from "./urls";

type Props = {
  runs: RunRow[];
  selectedRun: RunRow | null;
  spans: SpanNode[];
  selectedSpan: SpanNode | null;
  totalRunDurationMs: number | null;
};

const INDENT_PX = 16;
const BASE_PAD_PX = 12;
const TICKS = 4;

export function SpanWaterfall({
  runs,
  selectedRun,
  spans,
  selectedSpan,
  totalRunDurationMs,
}: Props) {
  if (selectedRun === null) {
    return (
      <section className="pane trace-pane" id="trace" aria-label="Trace waterfall">
        <div className="pane-header">
          <div>
            <span className="pane-title">Trace</span>
            <span className="pane-subtitle">Waterfall</span>
          </div>
        </div>
        <div className="pane-body">
          <TraceEmpty hasRuns={runs.length > 0} />
        </div>
      </section>
    );
  }

  const totalLabel = formatDurationMs(totalRunDurationMs);

  return (
    <section className="pane trace-pane" id="trace" aria-label="Trace waterfall">
      <div className="pane-header">
        <div>
          <span className="pane-title">
            <StatusDot status={selectedRun.status} />
            {selectedRun.workflow}
          </span>
          <span className="pane-subtitle">Trace waterfall</span>
        </div>
        <span className="pane-meta">
          <span>{selectedRun.id}</span>
          <span aria-hidden="true">·</span>
          <span>
            {spans.length} {spans.length === 1 ? "span" : "spans"}
          </span>
          <span aria-hidden="true">·</span>
          <span>{totalLabel}</span>
        </span>
      </div>
      <div className="pane-body">
        {spans.length === 0 ? (
          <SpansEmpty />
        ) : (
          <>
            <Ruler totalMs={totalRunDurationMs} />
            <div className="span-list" role="list" aria-label="Span waterfall">
              {spans.map((span) => (
                <SpanRow
                  key={span.id}
                  span={span}
                  runId={selectedRun.id}
                  selected={selectedSpan !== null && span.id === selectedSpan.id}
                />
              ))}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

function Ruler({ totalMs }: { totalMs: number | null }) {
  return (
    <div className="trace-ruler" aria-hidden="true">
      <span>span</span>
      <span className="ruler-tag">duration</span>
      <span className="ruler-tag">cost</span>
      <div className="ruler-track">
        {Array.from({ length: TICKS }).map((_, index) => (
          <span className="ruler-tick" key={index}>
            {tickLabel(totalMs, index)}
          </span>
        ))}
      </div>
    </div>
  );
}

function tickLabel(totalMs: number | null, index: number): string {
  if (totalMs === null || totalMs <= 0) {
    return index === 0 ? "0s" : "";
  }
  const fraction = index / TICKS;
  return formatDurationMs(totalMs * fraction);
}

function SpanRow({
  span,
  runId,
  selected,
}: {
  span: SpanNode;
  runId: string;
  selected: boolean;
}) {
  const indent = BASE_PAD_PX + span.depth * INDENT_PX;
  const barWidth = Math.max(span.widthPct, 1.5);

  return (
    <Link
      role="listitem"
      className={`span-row s-${span.status} ${selected ? "is-selected" : ""}`.trim()}
      href={spanHref(runId, span.id)}
      aria-current={selected ? "true" : undefined}
      aria-label={`Open span ${span.name}`}
    >
      <div className="span-name" style={{ paddingLeft: indent }}>
        <StatusDot status={span.status} />
        <div className="span-name-text">
          <strong>{span.name}</strong>
          <span className="span-kind">
            {span.kind} · {span.runtimeLabel}
          </span>
        </div>
      </div>
      <span className="span-mono">{formatDurationMs(span.durationMs)}</span>
      <span className="span-mono">{formatCostUSD(span.costUsd)}</span>
      <div className="span-bar-track" aria-hidden="true">
        <span
          className={`span-bar b-${span.status}`}
          style={{ left: `${span.offsetPct}%`, width: `${barWidth}%` }}
        />
      </div>
    </Link>
  );
}

function SpansEmpty() {
  return (
    <div className="empty">
      <strong>No spans recorded</strong>
      The runtime did not emit any spans for this run.
    </div>
  );
}

function TraceEmpty({ hasRuns }: { hasRuns: boolean }) {
  if (hasRuns) {
    return (
      <div className="empty">
        <strong>Select a run</strong>
        Pick a run from the list to inspect its trace.
      </div>
    );
  }
  return (
    <div className="empty">
      <strong>No runs yet</strong>
      A trace will appear once an agent run completes.
    </div>
  );
}
