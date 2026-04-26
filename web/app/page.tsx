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

export default async function Page() {
  const { runs, spans, summary } = await getOpsCanvasData();

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
            <h1>refund-resolution</h1>
          </div>
          <label className="search">
            <span>Search</span>
            <input defaultValue="status:failed tenant:northstar" aria-label="Search runs and spans" />
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
                          <strong>{run.name}</strong>
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
              <span>18.42s total</span>
            </div>
            <div className="timeline-ruler" aria-hidden="true">
              <span>0s</span>
              <span>6s</span>
              <span>12s</span>
              <span>18s</span>
            </div>
            <div className="span-table">
              {spans.map((span) => (
                <div className={`span-row ${statusTone(span.status)}`} key={`${span.name}-${span.depth}`}>
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
              <span>tool_call</span>
            </div>
            <dl className="detail-list">
              <div>
                <dt>Name</dt>
                <dd>currency_convert</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd className="danger">failed</dd>
              </div>
              <div>
                <dt>Runtime</dt>
                <dd>mcp:finance</dd>
              </div>
              <div>
                <dt>Duration</dt>
                <dd>3.84s</dd>
              </div>
              <div>
                <dt>Cost</dt>
                <dd>$0.01</dd>
              </div>
              <div>
                <dt>Redaction</dt>
                <dd>policy_v3 active</dd>
              </div>
            </dl>
            <div className="events">
              <h3>Events</h3>
              <ol>
                <li>
                  <span>+2.101s</span>
                  <strong>request.started</strong>
                </li>
                <li>
                  <span>+4.903s</span>
                  <strong>retry.scheduled</strong>
                </li>
                <li>
                  <span>+5.941s</span>
                  <strong>tool.error</strong>
                </li>
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
