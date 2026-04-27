import { getOpsCanvasData } from "./data";
import { RunTable } from "./RunTable";
import { SpanDetail } from "./SpanDetail";
import { SpanWaterfall } from "./SpanWaterfall";
import { SummaryStrip } from "./SummaryStrip";
import { Topbar } from "./Topbar";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

type PageProps = {
  searchParams?: Promise<SearchParams>;
};

function readParam(
  params: SearchParams | undefined,
  key: string,
): string | undefined {
  const value = params?.[key];
  if (Array.isArray(value)) {
    return value[0];
  }
  return value;
}

export default async function Page({ searchParams }: PageProps) {
  const params = (await searchParams) ?? {};
  const requestedRunId = readParam(params, "runId");
  const requestedSpanId = readParam(params, "spanId");

  const data = await getOpsCanvasData(requestedRunId, requestedSpanId);

  return (
    <>
      <main className="shell" aria-label="OpsCanvas">
        <Topbar apiState={data.apiState} />
        {data.apiState.mode === "error" && data.apiState.errorMessage !== null ? (
          <div className="error-banner" role="status" aria-live="polite">
            <span className="chip-dot" aria-hidden="true" />
            {data.apiState.errorMessage} Showing fallback data.
          </div>
        ) : null}
        <SummaryStrip metrics={data.metrics} />
        <div className="content">
          <section className="pane" aria-label="Recent runs">
            <div className="pane-header">
              <span className="pane-title">Runs</span>
              <span className="pane-meta">
                {data.runs.length} {data.runs.length === 1 ? "run" : "runs"}
              </span>
            </div>
            <div className="pane-body">
              <RunTable runs={data.runs} selectedRunId={data.selectedRunId} />
            </div>
          </section>
          <SpanWaterfall
            runs={data.runs}
            selectedRun={data.selectedRun}
            spans={data.spans}
            selectedSpan={data.selectedSpan}
            totalRunDurationMs={data.totalRunDurationMs}
          />
          <SpanDetail selectedRun={data.selectedRun} selectedSpan={data.selectedSpan} />
        </div>
      </main>
      <div className="narrow-message" role="status">
        <p>
          <strong>OpsCanvas is best viewed on a desktop.</strong>
          <br />
          Trace tables and span waterfalls need at least 1024px of horizontal space.
        </p>
      </div>
    </>
  );
}
