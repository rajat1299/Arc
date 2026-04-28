import type { ApiState, RunRow, SpanNode } from "./data";
import { ThemeToggle } from "./ThemeToggle";

type Props = {
  apiState: ApiState;
  selectedRun: RunRow | null;
  selectedSpan: SpanNode | null;
};

export function Topbar({ apiState, selectedRun, selectedSpan }: Props) {
  return (
    <header className="topbar" role="banner">
      <div className="topbar-location" aria-label="Current location">
        <span>Observability</span>
        <span aria-hidden="true">/</span>
        <strong>{selectedRun?.workflow ?? "Runs"}</strong>
        {selectedRun !== null ? <code>{selectedRun.id}</code> : null}
      </div>
      <div className="topbar-meta">
        <span className="topbar-context">
          {selectedSpan === null ? "No span selected" : selectedSpan.kind.replaceAll("_", " ")}
        </span>
        <ThemeToggle />
        <StateChip apiState={apiState} />
      </div>
    </header>
  );
}

export function StateChip({ apiState }: { apiState: ApiState }) {
  if (apiState.mode === "live") {
    return (
      <>
        <span className="chip chip-live" aria-label="Live API">
          <span className="chip-dot" aria-hidden="true" />
          Live
        </span>
        {apiState.host !== null ? <span className="host-tag">{apiState.host}</span> : null}
      </>
    );
  }

  if (apiState.mode === "error") {
    return (
      <>
        <span className="chip chip-error" aria-label="API unreachable, showing fallback data">
          <span className="chip-dot" aria-hidden="true" />
          API offline
        </span>
        {apiState.host !== null ? <span className="host-tag">{apiState.host}</span> : null}
      </>
    );
  }

  return (
    <span className="chip chip-mock" aria-label="Mock data, no API configured">
      <span className="chip-dot" aria-hidden="true" />
      Mock data
    </span>
  );
}
