import { getOpsCanvasData } from "./data";
import { ResizablePanels } from "./ResizablePanels";
import { RunTable } from "./RunTable";
import { Sidebar } from "./Sidebar";
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
        <Sidebar apiState={data.apiState} metrics={data.metrics} selectedRun={data.selectedRun} />
        <section className="workspace" aria-label="OpsCanvas workspace">
          <Topbar
            apiState={data.apiState}
            selectedRun={data.selectedRun}
            selectedSpan={data.selectedSpan}
          />
          {data.apiState.mode === "error" && data.apiState.errorMessage !== null ? (
            <div className="error-banner" role="status" aria-live="polite">
              <span className="chip-dot" aria-hidden="true" />
              {data.apiState.errorMessage} Showing fallback data.
            </div>
          ) : null}
          <SummaryStrip metrics={data.metrics} />
          <ResizablePanels
            runs={
              <section className="pane runs-pane" id="runs" aria-label="Recent runs">
                <div className="pane-header">
                  <div>
                    <span className="pane-title">Runs</span>
                    <span className="pane-subtitle">Latest agent workflows</span>
                  </div>
                  <span className="pane-meta">
                    {data.runs.length} {data.runs.length === 1 ? "run" : "runs"}
                  </span>
                </div>
                <div className="pane-body">
                  <RunTable runs={data.runs} selectedRunId={data.selectedRunId} />
                </div>
              </section>
            }
            trace={
              <SpanWaterfall
                runs={data.runs}
                selectedRun={data.selectedRun}
                spans={data.spans}
                selectedSpan={data.selectedSpan}
                totalRunDurationMs={data.totalRunDurationMs}
              />
            }
            detail={<SpanDetail selectedRun={data.selectedRun} selectedSpan={data.selectedSpan} />}
          />
        </section>
      </main>
      <div className="narrow-message" role="status">
        <p>
          <strong>OpsCanvas is best viewed on a desktop.</strong>
          <br />
          Trace tables and span waterfalls need at least 1200px of horizontal space.
        </p>
      </div>
    </>
  );
}
