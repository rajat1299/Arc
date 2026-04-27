import type { ApiState } from "./data";

type Props = {
  apiState: ApiState;
};

export function Topbar({ apiState }: Props) {
  return (
    <header className="topbar" role="banner">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          OC
        </span>
        <span>OpsCanvas</span>
      </div>
      <div className="topbar-meta">
        <StateChip apiState={apiState} />
      </div>
    </header>
  );
}

function StateChip({ apiState }: { apiState: ApiState }) {
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
