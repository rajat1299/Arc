import type { RunRow, SpanNode } from "./data";
import { formatCostUSD, formatDurationMs, formatTokens } from "./format";
import { JsonView } from "./JsonView";

type Props = {
  selectedRun: RunRow | null;
  selectedSpan: SpanNode | null;
};

export function SpanDetail({ selectedRun, selectedSpan }: Props) {
  return (
    <aside className="pane" aria-label="Selected span detail">
      <div className="pane-header">
        <span className="pane-title">Span</span>
      </div>
      <div className="pane-body">
        {selectedSpan === null || selectedRun === null ? (
          <DetailEmpty />
        ) : (
          <DetailContent run={selectedRun} span={selectedSpan} />
        )}
        <section data-future-feature="v1.5" aria-hidden="true">
          Improvement suggestions ship in v1.5
        </section>
      </div>
    </aside>
  );
}

function DetailContent({ run, span }: { run: RunRow; span: SpanNode }) {
  const hasInput = !isEmptyValue(span.inputData);
  const hasOutput = !isEmptyValue(span.outputData);
  const hasAttributes = Object.keys(span.attributes).length > 0;

  return (
    <>
      <header className="detail-title">
        <div className="detail-title-name">{span.name}</div>
        <div className="detail-title-kind">
          <span>{span.kind}</span>
          <span aria-hidden="true">·</span>
          <span>{span.runtimeLabel}</span>
        </div>
      </header>

      <section className="detail-section" aria-label="Span properties">
        <dl className="kv">
          <dt>Status</dt>
          <dd
            className={
              span.status === "failed"
                ? "fg-danger"
                : span.status === "suboptimal"
                  ? "fg-warning"
                  : "fg-primary"
            }
          >
            {span.status}
          </dd>

          <dt>Span ID</dt>
          <dd>{span.id}</dd>

          <dt>Parent</dt>
          <dd>{span.parentId ?? "—"}</dd>

          <dt>Run</dt>
          <dd>{run.id}</dd>

          <dt>Duration</dt>
          <dd>{formatDurationMs(span.durationMs)}</dd>

          <dt>Cost</dt>
          <dd>{formatCostUSD(span.costUsd)}</dd>

          <dt>Tokens</dt>
          <dd>{formatTokens(span.totalTokens)}</dd>
        </dl>
      </section>

      {span.errorMessage !== null ? (
        <section className="detail-section" aria-label="Error">
          <h3>Error</h3>
          <div className="error-block">{span.errorMessage}</div>
        </section>
      ) : null}

      {hasAttributes ? (
        <section className="detail-section" aria-label="Attributes">
          <h3>Attributes</h3>
          <JsonView value={span.attributes} />
        </section>
      ) : null}

      {hasInput ? (
        <section className="detail-section" aria-label="Input">
          <details className="collapsible">
            <summary>Input</summary>
            <div className="collapsible-body">
              <JsonView value={span.inputData} />
            </div>
          </details>
        </section>
      ) : null}

      {hasOutput ? (
        <section className="detail-section" aria-label="Output">
          <details className="collapsible">
            <summary>Output</summary>
            <div className="collapsible-body">
              <JsonView value={span.outputData} />
            </div>
          </details>
        </section>
      ) : null}

      {span.events.length > 0 ? (
        <section className="detail-section" aria-label="Events">
          <h3>Events</h3>
          <ol className="events-list">
            {span.events.map((event) => {
              const isError = /error|failed/i.test(event.name);
              return (
                <li className="events-item" key={event.id}>
                  <span className="events-time">{event.offset}</span>
                  <span className={`events-name${isError ? " is-error" : ""}`}>
                    {event.name}
                  </span>
                </li>
              );
            })}
          </ol>
        </section>
      ) : null}
    </>
  );
}

function DetailEmpty() {
  return (
    <div className="empty">
      <strong>No span selected</strong>
      Select a span from the trace to inspect its attributes, events, and usage.
    </div>
  );
}

function isEmptyValue(value: unknown): boolean {
  if (value === null || value === undefined) {
    return true;
  }
  if (typeof value === "string") {
    return value.length === 0;
  }
  if (Array.isArray(value)) {
    return value.length === 0;
  }
  if (typeof value === "object") {
    return Object.keys(value as Record<string, unknown>).length === 0;
  }
  return false;
}
