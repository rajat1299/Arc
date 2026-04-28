import type { ApiState, MetricsSummary, RunRow } from "./data";
import { formatCostUSD } from "./format";
import { StatusDot } from "./StatusDot";

type Props = {
  apiState: ApiState;
  metrics: MetricsSummary | null;
  selectedRun: RunRow | null;
};

const navItems = [
  { href: "#runs", label: "Runs", meta: "Feed" },
  { href: "#trace", label: "Trace", meta: "Waterfall" },
  { href: "#span-detail", label: "Span", meta: "Detail" },
];

export function Sidebar({ apiState, metrics, selectedRun }: Props) {
  return (
    <aside className="sidebar" aria-label="OpsCanvas navigation">
      <div className="sidebar-brand">
        <span className="brand-mark" aria-hidden="true">
          OC
        </span>
        <div className="sidebar-brand-copy">
          <strong>OpsCanvas</strong>
          <span>{apiStateLabel(apiState)}</span>
        </div>
      </div>

      <nav className="sidebar-nav" aria-label="Workspace sections">
        <span className="sidebar-section-label">Workspace</span>
        {navItems.map((item) => (
          <a className="sidebar-link" href={item.href} key={item.href}>
            <span>{item.label}</span>
            <span>{item.meta}</span>
          </a>
        ))}
      </nav>

      <div className="sidebar-block" aria-label="Selected run">
        <span className="sidebar-section-label">Active Run</span>
        {selectedRun === null ? (
          <p className="sidebar-muted">No run selected</p>
        ) : (
          <div className="sidebar-run">
            <div className="sidebar-run-title">
              <StatusDot status={selectedRun.status} />
              <span>{selectedRun.workflow}</span>
            </div>
            <span>{selectedRun.id}</span>
            <span>{selectedRun.runtime}</span>
          </div>
        )}
      </div>

      <div className="sidebar-footer" aria-label="Operational summary">
        <div>
          <span className="sidebar-section-label">Last 24h</span>
          <strong>{metrics === null ? "—" : metrics.totalRuns.toLocaleString("en-US")}</strong>
          <span>runs</span>
        </div>
        <div>
          <span className="sidebar-section-label">Spend</span>
          <strong>{metrics === null ? "—" : formatCostUSD(metrics.totalCostUsd)}</strong>
          <span>tracked</span>
        </div>
      </div>
    </aside>
  );
}

function apiStateLabel(apiState: ApiState): string {
  if (apiState.mode === "live") {
    return apiState.host ?? "Live API";
  }
  if (apiState.mode === "error") {
    return "API offline";
  }
  return "Mock dataset";
}
