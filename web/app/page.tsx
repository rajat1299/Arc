import { type DisplayStatus, getOpsCanvasData } from "./data";

export const dynamic = "force-dynamic";

function statusTone(status: DisplayStatus) {
  if (status === "suboptimal" || status === "interrupted") {
    return "warning";
  }

  return status;
}

function StatusDot({ status }: { status: DisplayStatus }) {
  return <span className={`status-dot ${statusTone(status)}`} aria-label={status} />;
}

type PageProps = {
  searchParams?: Promise<{
    runId?: string | string[];
  }>;
};

function readRunId(params: { runId?: string | string[] } | undefined): string | undefined {
  const runId = params?.runId;

  if (Array.isArray(runId)) {
    return runId[0];
  }

  return runId;
}

export default async function Page({ searchParams }: PageProps) {
  const requestedRunId = readRunId(await searchParams);
  const { runs, spans, summary, selectedRunId, selectedRun, selectedSpan, totalDuration } =
    await getOpsCanvasData(requestedRunId);

  return (
    <main className="ops-shell">
      <aside className="sidebar" aria-label="Workspace navigation">
        <div className="brand">
          <span className="brand-mark">A</span>
          <span>Arc</span>
        </div>
        <nav className="nav-list">
          {["Runs", "Traces", "Evals", "Cost", "Settings"].map((item) => (
            <a className={item === "Traces" ? "active" : ""} href="#" key={item}>
              {item}
            </a>
          ))}
        </nav>
        <div className="environment">
          <span>Project</span>
          <strong>Production agents</strong>
          <span>prod / us-central</span>
        </div>
      </aside>

      <section className="workspace" aria-label="Trace operations workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Trace detail</p>
            <h1>{selectedRun.name}</h1>
          </div>
          <label className="search">
            <span>Search</span>
            <input defaultValue={`status:${selectedRun.status} tenant:${selectedRun.tenant}`} aria-label="Search runs and spans" />
          </label>
          <div className="toolbar-meta">
            <span>Cmd K</span>
            <button>Replay</button>
          </div>
        </header>

        <div className="summary-strip" aria-label="Cost and evaluation summary">
          {summary.map((item) => (
            <div className="metric" key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <em>{item.delta}</em>
            </div>
          ))}
        </div>

        <div className="content-grid">
          <section className="run-list" aria-label="Run search results">
            <div className="panel-heading">
              <h2>Runs</h2>
              <span>Failed view</span>
            </div>
            <table className="run-table" aria-label="Recent runs">
              <thead>
                <tr>
                  <th scope="col">Status</th>
                  <th scope="col">Run</th>
                  <th scope="col">Tenant</th>
                  <th scope="col">Runtime</th>
                  <th scope="col">Duration</th>
                  <th scope="col">Cost</th>
                  <th scope="col">Started</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <span className="status-label">
                        <StatusDot status={run.status} />
                        {run.status}
                      </span>
                    </td>
                    <td>
                      <div className="run-primary">
                        <div>
                          <strong>
                            <a href={`?runId=${encodeURIComponent(run.id)}`} aria-current={run.id === selectedRunId ? "page" : undefined}>
                              {run.name}
                            </a>
                          </strong>
                          <span>{run.id}</span>
                        </div>
                      </div>
                    </td>
                    <td>{run.tenant}</td>
                    <td>{run.runtime}</td>
                    <td>{run.duration}</td>
                    <td>{run.cost}</td>
                    <td>{run.started}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="span-panel" aria-label="Span tree and waterfall">
            <div className="panel-heading">
              <h2>Span tree</h2>
              <span>{totalDuration} total</span>
            </div>
            <div className="timeline-ruler" aria-hidden="true">
              <span>0s</span>
              <span>6s</span>
              <span>12s</span>
              <span>18s</span>
            </div>
            <div className="span-table">
              {spans.map((span) => (
                <div className={`span-row ${statusTone(span.status)}`} key={span.id}>
                  <div className="span-name" style={{ paddingLeft: `${span.depth * 18 + 8}px` }}>
                    <StatusDot status={span.status} />
                    <div>
                      <strong>{span.name}</strong>
                      <span>
                        {span.kind} / {span.runtime}
                      </span>
                    </div>
                  </div>
                  <span className="duration">{span.duration}</span>
                  <span className="cost">{span.cost}</span>
                  <div className="waterfall" aria-hidden="true">
                    <span style={{ left: `${span.offset}%`, width: `${span.width}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </section>

          <aside className="detail-panel" aria-label="Selected span detail">
            <div className="panel-heading">
              <h2>Span detail</h2>
              <span>{selectedSpan.kind}</span>
            </div>
            <dl className="detail-list">
              <div>
                <dt>Name</dt>
                <dd>{selectedSpan.name}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd className={selectedSpan.status === "failed" ? "danger" : undefined}>{selectedSpan.status}</dd>
              </div>
              <div>
                <dt>Runtime</dt>
                <dd>{selectedSpan.runtime}</dd>
              </div>
              <div>
                <dt>Duration</dt>
                <dd>{selectedSpan.duration}</dd>
              </div>
              <div>
                <dt>Cost</dt>
                <dd>{selectedSpan.cost}</dd>
              </div>
              <div>
                <dt>Run</dt>
                <dd>{selectedRun.id}</dd>
              </div>
            </dl>
            <div className="events">
              <h3>Events</h3>
              <ol>
                {selectedSpan.events.length === 0 ? (
                  <li>
                    <span>+0.000s</span>
                    <strong>no events</strong>
                  </li>
                ) : (
                  selectedSpan.events.map((event) => (
                    <li key={event.id}>
                      <span>{event.offset}</span>
                      <strong>{event.name}</strong>
                    </li>
                  ))
                )}
              </ol>
            </div>
            <div className="suggestion">
              <p className="eyebrow">Improvement queue</p>
              <h3>Retry fixed-rate fallback on EUR conversion failures.</h3>
              <div className="evidence">
                <span>Eval delta</span>
                <strong>+6.2%</strong>
                <span>Cost delta</span>
                <strong>+$0.02/run</strong>
              </div>
            </div>
          </aside>
        </div>
      </section>
    </main>
  );
}
