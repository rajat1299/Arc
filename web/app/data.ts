import { durationMsBetween, formatEventOffset, formatRelativeTime } from "./format";
import { redactRecord, redactValue } from "./redact";

/* ------------------------------------------------------------------ */
/*  Canonical API contracts (mirror packages/opscanvas-core/.../events.py) */
/* ------------------------------------------------------------------ */

export type ApiRunStatus = "succeeded" | "failed" | "interrupted" | "suboptimal" | "running";

export type ApiSpanKind =
  | "agent"
  | "model_call"
  | "tool_call"
  | "handoff"
  | "guardrail"
  | "mcp_list"
  | "sandbox_op"
  | "retry"
  | "custom";

export type ApiUsage = {
  input_tokens: number | null;
  output_tokens: number | null;
  cached_input_tokens: number | null;
  reasoning_tokens: number | null;
  total_tokens: number | null;
  cost_usd: number | null;
};

export type ApiSpanEvent = {
  id: string;
  span_id: string;
  name: string;
  timestamp: string;
  attributes: Record<string, unknown>;
};

export type ApiSpan = {
  id: string;
  run_id: string;
  kind: ApiSpanKind;
  name: string;
  parent_id: string | null;
  started_at: string;
  ended_at: string | null;
  usage: ApiUsage | null;
  input?: unknown;
  output?: unknown;
  input_data?: unknown;
  output_data?: unknown;
  attributes: Record<string, unknown>;
  events: ApiSpanEvent[];
};

export type ApiRun = {
  id: string;
  schema_version: string;
  status: ApiRunStatus;
  started_at: string;
  ended_at: string | null;
  runtime: string;
  project_id: string | null;
  environment: string | null;
  tenant_id: string | null;
  user_id: string | null;
  workflow_name: string | null;
  usage: ApiUsage | null;
  metadata: Record<string, unknown>;
  spans: ApiSpan[];
};

export type ApiRunSummary = {
  id: string;
  schema_version: string;
  status: ApiRunStatus;
  runtime: string;
  started_at: string;
  ended_at: string | null;
  tenant_id: string | null;
  environment: string | null;
  workflow_name: string | null;
  span_count: number;
  event_count: number;
  cost_usd: number | null;
  total_tokens: number | null;
};

export type ApiRunMetrics = {
  run_count: number;
  failed_count: number;
  running_count: number;
  suboptimal_count: number;
  total_cost_usd: number;
  total_tokens: number;
  p95_latency_ms: number | null;
};

/* ------------------------------------------------------------------ */
/*  View models                                                        */
/* ------------------------------------------------------------------ */

export type AppMode = "live" | "mock" | "error";

export type ApiState = {
  mode: AppMode;
  host: string | null;
  errorMessage: string | null;
};

export type RunRow = {
  id: string;
  workflow: string;
  status: ApiRunStatus;
  runtime: string;
  tenant: string;
  environment: string | null;
  startedAtIso: string;
  startedRelative: string;
  durationMs: number | null;
  costUsd: number | null;
  totalTokens: number | null;
  spanCount: number;
  eventCount: number;
};

export type SpanEventNode = {
  id: string;
  name: string;
  offset: string;
  attributes: Record<string, unknown>;
};

export type SpanNode = {
  id: string;
  parentId: string | null;
  depth: number;
  name: string;
  kind: ApiSpanKind;
  runtimeLabel: string;
  status: ApiRunStatus;
  durationMs: number | null;
  costUsd: number | null;
  totalTokens: number | null;
  offsetPct: number;
  widthPct: number;
  attributes: Record<string, unknown>;
  inputData: unknown;
  outputData: unknown;
  events: SpanEventNode[];
  errorMessage: string | null;
};

export type MetricsSummary = {
  totalRuns: number;
  failedRuns: number;
  suboptimalRuns: number;
  runningRuns: number;
  totalCostUsd: number;
  totalTokens: number;
  p95LatencyMs: number | null;
};

export type OpsCanvasData = {
  apiState: ApiState;
  runs: RunRow[];
  spans: SpanNode[];
  metrics: MetricsSummary | null;
  selectedRunId: string | null;
  selectedRun: RunRow | null;
  selectedSpan: SpanNode | null;
  totalRunDurationMs: number | null;
  generatedAt: number;
};

/* ------------------------------------------------------------------ */
/*  Fetcher                                                            */
/* ------------------------------------------------------------------ */

const RUNS_FETCH_TIMEOUT_MS = 1500;
const DETAIL_FETCH_TIMEOUT_MS = 1500;

export async function getOpsCanvasData(
  requestedRunId: string | undefined,
  requestedSpanId: string | undefined,
): Promise<OpsCanvasData> {
  const baseUrl = process.env.OPSCANVAS_API_BASE_URL?.trim();
  const generatedAt = Date.now();

  if (!baseUrl) {
    return mockData(requestedRunId, requestedSpanId, generatedAt, {
      mode: "mock",
      host: null,
      errorMessage: null,
    });
  }

  const host = safeHost(baseUrl);
  const apiKey = process.env.OPSCANVAS_API_KEY?.trim() || null;

  const summaries = await fetchRunSummaries(baseUrl, apiKey);
  if (summaries === null) {
    return mockData(requestedRunId, requestedSpanId, generatedAt, {
      mode: "error",
      host,
      errorMessage: `Could not reach API at ${host ?? baseUrl}.`,
    });
  }

  const sortedSummaries = [...summaries].sort(
    (a, b) => Date.parse(b.started_at) - Date.parse(a.started_at),
  );

  const runs = sortedSummaries.map(toRunRow.bind(null, generatedAt));
  const selectedSummary = chooseSelectedSummary(sortedSummaries, requestedRunId);

  if (selectedSummary === null) {
    return {
      apiState: { mode: "live", host, errorMessage: null },
      runs,
      spans: [],
      metrics: null,
      selectedRunId: null,
      selectedRun: null,
      selectedSpan: null,
      totalRunDurationMs: null,
      generatedAt,
    };
  }

  const [run, apiSpans, apiMetrics] = await Promise.all([
    fetchRun(baseUrl, apiKey, selectedSummary.id),
    fetchRunSpans(baseUrl, apiKey, selectedSummary.id),
    fetchRunMetrics(baseUrl, apiKey),
  ]);

  const spanSource = apiSpans ?? run?.spans ?? [];
  const referenceRun: ApiRun | ApiRunSummary = run ?? selectedSummary;
  const spans = mapSpans(spanSource, referenceRun);
  const selectedRun = selectedRunRow(runs, selectedSummary, run, generatedAt);
  const selectedSpan = chooseSelectedSpan(spans, requestedSpanId);

  return {
    apiState: { mode: "live", host, errorMessage: null },
    runs,
    spans,
    metrics: apiMetrics === null ? null : toMetricsSummary(apiMetrics),
    selectedRunId: selectedRun?.id ?? null,
    selectedRun,
    selectedSpan,
    totalRunDurationMs: durationMsBetween(referenceRun.started_at, referenceRun.ended_at),
    generatedAt,
  };
}

function safeHost(baseUrl: string): string | null {
  try {
    return new URL(baseUrl).host;
  } catch {
    return null;
  }
}

function selectedRunRow(
  runs: RunRow[],
  summary: ApiRunSummary,
  detail: ApiRun | null,
  generatedAt: number,
): RunRow {
  const fromList = runs.find((row) => row.id === summary.id);
  if (fromList === undefined) {
    return toRunRow(generatedAt, summary);
  }
  if (detail === null) {
    return fromList;
  }
  return {
    ...fromList,
    workflow: detail.workflow_name ?? fromList.workflow,
    tenant: detail.tenant_id ?? fromList.tenant,
    environment: detail.environment ?? fromList.environment,
    runtime: detail.runtime ?? fromList.runtime,
    durationMs:
      durationMsBetween(detail.started_at, detail.ended_at) ?? fromList.durationMs,
    costUsd: detail.usage?.cost_usd ?? fromList.costUsd,
    totalTokens: detail.usage?.total_tokens ?? fromList.totalTokens,
    spanCount: detail.spans.length,
    eventCount: detail.spans.reduce((acc, span) => acc + span.events.length, 0),
  };
}

function chooseSelectedSummary(
  summaries: ApiRunSummary[],
  requestedRunId: string | undefined,
): ApiRunSummary | null {
  if (summaries.length === 0) {
    return null;
  }
  if (requestedRunId !== undefined) {
    const requested = summaries.find((summary) => summary.id === requestedRunId);
    if (requested !== undefined) {
      return requested;
    }
  }
  const failed = summaries.find((summary) => summary.status === "failed");
  if (failed !== undefined) {
    return failed;
  }
  const suboptimal = summaries.find((summary) => summary.status === "suboptimal");
  if (suboptimal !== undefined) {
    return suboptimal;
  }
  return summaries[0];
}

function chooseSelectedSpan(
  spans: SpanNode[],
  requestedSpanId: string | undefined,
): SpanNode | null {
  if (spans.length === 0) {
    return null;
  }
  if (requestedSpanId !== undefined) {
    const requested = spans.find((span) => span.id === requestedSpanId);
    if (requested !== undefined) {
      return requested;
    }
  }
  const failed = spans.find((span) => span.status === "failed");
  if (failed !== undefined) {
    return failed;
  }
  const suboptimal = spans.find(
    (span) => span.status === "suboptimal" || span.status === "interrupted",
  );
  if (suboptimal !== undefined) {
    return suboptimal;
  }
  const root = spans.find((span) => span.parentId === null);
  return root ?? spans[0];
}

function toRunRow(generatedAt: number, summary: ApiRunSummary): RunRow {
  return {
    id: summary.id,
    workflow: summary.workflow_name ?? summary.id,
    status: summary.status,
    runtime: summary.runtime,
    tenant: summary.tenant_id ?? "—",
    environment: summary.environment,
    startedAtIso: summary.started_at,
    startedRelative: formatRelativeTime(summary.started_at, generatedAt),
    durationMs: durationMsBetween(summary.started_at, summary.ended_at),
    costUsd: summary.cost_usd,
    totalTokens: summary.total_tokens,
    spanCount: summary.span_count,
    eventCount: summary.event_count,
  };
}

function mapSpans(spans: ApiSpan[], run: ApiRun | ApiRunSummary): SpanNode[] {
  const depthById = new Map<string, number>();
  const spanById = new Map(spans.map((span) => [span.id, span]));
  const runStarted = parseTime(run.started_at);
  const runEnded = parseTime(run.ended_at);
  const spanTimes = spans.flatMap((span) => {
    const started = parseTime(span.started_at);
    if (started === null) {
      return [];
    }
    return [{ started, ended: parseTime(span.ended_at) }];
  });
  const timelineStart = runStarted ?? spanTimes[0]?.started ?? 0;
  const timelineEnd =
    runEnded ??
    Math.max(
      timelineStart + 1,
      ...spanTimes.map(({ started, ended }) => ended ?? started + 1),
    );
  const timelineMs = Math.max(timelineEnd - timelineStart, 1);

  return spans.map((span) => {
    const depth = getSpanDepth(span, spanById, depthById);
    const started = parseTime(span.started_at);
    const ended = parseTime(span.ended_at);
    const offsetPct = started === null ? 0 : clampPercent(((started - timelineStart) / timelineMs) * 100);
    const widthPctRaw =
      started === null || ended === null || ended < started
        ? 2
        : ((ended - started) / timelineMs) * 100;
    const widthPct = Math.max(2, Math.min(clampPercent(widthPctRaw), 100 - offsetPct));

    return {
      id: span.id,
      parentId: span.parent_id,
      depth,
      name: span.name,
      kind: span.kind,
      runtimeLabel: spanRuntimeLabel(span),
      status: spanStatus(span, run.status),
      durationMs: durationMsBetween(span.started_at, span.ended_at),
      costUsd: span.usage?.cost_usd ?? null,
      totalTokens: span.usage?.total_tokens ?? null,
      offsetPct,
      widthPct,
      attributes: redactRecord(span.attributes),
      inputData: redactValue(span.input ?? span.input_data ?? null),
      outputData: redactValue(span.output ?? span.output_data ?? null),
      events: span.events.map((event) => ({
        id: event.id,
        name: event.name,
        offset: formatEventOffset(event.timestamp, span.started_at),
        attributes: redactRecord(event.attributes),
      })),
      errorMessage: extractErrorMessage(span),
    };
  });
}

function toMetricsSummary(metrics: ApiRunMetrics): MetricsSummary {
  return {
    totalRuns: metrics.run_count,
    failedRuns: metrics.failed_count,
    suboptimalRuns: metrics.suboptimal_count,
    runningRuns: metrics.running_count,
    totalCostUsd: metrics.total_cost_usd,
    totalTokens: metrics.total_tokens,
    p95LatencyMs: metrics.p95_latency_ms,
  };
}

function spanRuntimeLabel(span: ApiSpan): string {
  return firstString(
    span.attributes.runtime,
    span.attributes.model,
    span.attributes["agent.model"],
    span.attributes.tool,
    span.attributes.provider,
    span.kind,
  );
}

function spanStatus(span: ApiSpan, runStatus: ApiRunStatus): ApiRunStatus {
  const status = span.attributes.status;
  if (isApiRunStatus(status)) {
    return status;
  }
  if (hasSuboptimalSignal(span)) {
    return "suboptimal";
  }
  if (
    span.events.some(
      (event) => event.name.includes("error") || event.name.includes("failed"),
    )
  ) {
    return "failed";
  }
  return runStatus === "failed" && span.parent_id === null ? "failed" : "succeeded";
}

function hasSuboptimalSignal(span: ApiSpan): boolean {
  const failure = span.attributes.failure;
  return (
    span.attributes["failure.severity"] === "suboptimal" ||
    span.attributes.severity === "suboptimal" ||
    (isRecord(failure) && failure.severity === "suboptimal") ||
    span.events.some((event) => event.name === "quality.suboptimal_detected")
  );
}

function extractErrorMessage(span: ApiSpan): string | null {
  if (typeof span.attributes.error === "string" && span.attributes.error.length > 0) {
    return span.attributes.error;
  }
  if (typeof span.attributes["error.message"] === "string") {
    return span.attributes["error.message"] as string;
  }
  const errorEvent = span.events.find(
    (event) => event.name.includes("error") || event.name.includes("failed"),
  );
  if (errorEvent !== undefined) {
    const message = errorEvent.attributes?.message;
    if (typeof message === "string" && message.length > 0) {
      return message;
    }
    return errorEvent.name;
  }
  return null;
}

function getSpanDepth(
  span: ApiSpan,
  spanById: Map<string, ApiSpan>,
  depthById: Map<string, number>,
): number {
  const cached = depthById.get(span.id);
  if (cached !== undefined) {
    return cached;
  }

  let depth = 0;
  let current = span;
  const visited = new Set<string>();

  while (current.parent_id !== null) {
    if (visited.has(current.id)) {
      depthById.set(span.id, 0);
      return 0;
    }
    visited.add(current.id);

    const parent = spanById.get(current.parent_id);
    if (parent === undefined || visited.has(parent.id)) {
      depthById.set(span.id, 0);
      return 0;
    }

    const parentDepth = depthById.get(parent.id);
    if (parentDepth !== undefined) {
      depth += parentDepth + 1;
      depthById.set(span.id, depth);
      return depth;
    }

    depth += 1;
    current = parent;
  }

  depthById.set(span.id, depth);
  return depth;
}

function parseTime(value: string | null): number | null {
  if (value === null) {
    return null;
  }
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, value));
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.length > 0) {
      return value;
    }
  }
  return "—";
}

/* ------------------------------------------------------------------ */
/*  HTTP                                                               */
/* ------------------------------------------------------------------ */

async function fetchRunSummaries(baseUrl: string, apiKey: string | null): Promise<ApiRunSummary[] | null> {
  return fetchApiJson(baseUrl, apiKey, "/v1/runs", isApiRunSummaryList, RUNS_FETCH_TIMEOUT_MS);
}

async function fetchRun(
  baseUrl: string,
  apiKey: string | null,
  runId: string,
): Promise<ApiRun | null> {
  return fetchApiJson(
    baseUrl,
    apiKey,
    `/v1/runs/${encodeURIComponent(runId)}`,
    isApiRun,
    DETAIL_FETCH_TIMEOUT_MS,
  );
}

async function fetchRunSpans(
  baseUrl: string,
  apiKey: string | null,
  runId: string,
): Promise<ApiSpan[] | null> {
  return fetchApiJson(
    baseUrl,
    apiKey,
    `/v1/runs/${encodeURIComponent(runId)}/spans`,
    isApiSpanList,
    DETAIL_FETCH_TIMEOUT_MS,
  );
}

async function fetchRunMetrics(
  baseUrl: string,
  apiKey: string | null,
): Promise<ApiRunMetrics | null> {
  return fetchApiJson(baseUrl, apiKey, "/v1/runs/metrics", isApiRunMetrics, DETAIL_FETCH_TIMEOUT_MS);
}

async function fetchApiJson<T>(
  baseUrl: string,
  apiKey: string | null,
  path: string,
  validate: (payload: unknown) => payload is T,
  timeoutMs: number,
): Promise<T | null> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (apiKey !== null) {
    headers["Authorization"] = `Bearer ${apiKey}`;
  }

  try {
    const response = await fetch(new URL(path, baseUrl), {
      cache: "no-store",
      headers,
      signal: controller.signal,
    });
    if (!response.ok) {
      return null;
    }
    const payload: unknown = await response.json();
    return validate(payload) ? payload : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

/* ------------------------------------------------------------------ */
/*  Type guards                                                        */
/* ------------------------------------------------------------------ */

function isApiRunSummaryList(value: unknown): value is ApiRunSummary[] {
  return Array.isArray(value) && value.every(isApiRunSummary);
}

function isApiSpanList(value: unknown): value is ApiSpan[] {
  return Array.isArray(value) && value.every(isApiSpan);
}

function isApiRunSummary(value: unknown): value is ApiRunSummary {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    typeof value.schema_version === "string" &&
    isApiRunStatus(value.status) &&
    typeof value.runtime === "string" &&
    typeof value.started_at === "string" &&
    (typeof value.ended_at === "string" || value.ended_at === null) &&
    (typeof value.tenant_id === "string" || value.tenant_id === null) &&
    (typeof value.environment === "string" || value.environment === null) &&
    (typeof value.workflow_name === "string" || value.workflow_name === null) &&
    isNonNegativeInteger(value.span_count) &&
    isNonNegativeInteger(value.event_count) &&
    isNullableNonNegativeNumber(value.cost_usd) &&
    isNullableNonNegativeInteger(value.total_tokens)
  );
}

function isApiRun(value: unknown): value is ApiRun {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    typeof value.schema_version === "string" &&
    isApiRunStatus(value.status) &&
    typeof value.started_at === "string" &&
    (typeof value.ended_at === "string" || value.ended_at === null) &&
    typeof value.runtime === "string" &&
    (typeof value.project_id === "string" || value.project_id === null) &&
    (typeof value.environment === "string" || value.environment === null) &&
    (typeof value.tenant_id === "string" || value.tenant_id === null) &&
    (typeof value.user_id === "string" || value.user_id === null) &&
    (typeof value.workflow_name === "string" || value.workflow_name === null) &&
    (value.usage === null || isApiUsage(value.usage)) &&
    isRecord(value.metadata) &&
    Array.isArray(value.spans) &&
    value.spans.every(isApiSpan)
  );
}

function isApiSpan(value: unknown): value is ApiSpan {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    typeof value.run_id === "string" &&
    isApiSpanKind(value.kind) &&
    typeof value.name === "string" &&
    (typeof value.parent_id === "string" || value.parent_id === null) &&
    typeof value.started_at === "string" &&
    (typeof value.ended_at === "string" || value.ended_at === null) &&
    (value.usage === null || isApiUsage(value.usage)) &&
    isRecord(value.attributes) &&
    Array.isArray(value.events) &&
    value.events.every(isApiSpanEvent)
  );
}

function isApiUsage(value: unknown): value is ApiUsage {
  if (!isRecord(value)) {
    return false;
  }
  return (
    isNullableNonNegativeInteger(value.input_tokens) &&
    isNullableNonNegativeInteger(value.output_tokens) &&
    isNullableNonNegativeInteger(value.cached_input_tokens) &&
    isNullableNonNegativeInteger(value.reasoning_tokens) &&
    isNullableNonNegativeInteger(value.total_tokens) &&
    isNullableNonNegativeNumber(value.cost_usd)
  );
}

function isApiSpanEvent(value: unknown): value is ApiSpanEvent {
  if (!isRecord(value)) {
    return false;
  }
  return (
    typeof value.id === "string" &&
    typeof value.span_id === "string" &&
    typeof value.name === "string" &&
    typeof value.timestamp === "string" &&
    isRecord(value.attributes)
  );
}

function isApiRunMetrics(value: unknown): value is ApiRunMetrics {
  if (!isRecord(value)) {
    return false;
  }
  return (
    isNonNegativeInteger(value.run_count) &&
    isNonNegativeInteger(value.failed_count) &&
    isNonNegativeInteger(value.running_count) &&
    isNonNegativeInteger(value.suboptimal_count) &&
    isNonNegativeNumber(value.total_cost_usd) &&
    isNonNegativeInteger(value.total_tokens) &&
    isNullableNonNegativeInteger(value.p95_latency_ms)
  );
}

function isApiRunStatus(value: unknown): value is ApiRunStatus {
  return (
    value === "succeeded" ||
    value === "failed" ||
    value === "interrupted" ||
    value === "suboptimal" ||
    value === "running"
  );
}

function isApiSpanKind(value: unknown): value is ApiSpanKind {
  return (
    value === "agent" ||
    value === "model_call" ||
    value === "tool_call" ||
    value === "handoff" ||
    value === "guardrail" ||
    value === "mcp_list" ||
    value === "sandbox_op" ||
    value === "retry" ||
    value === "custom"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableNonNegativeNumber(value: unknown): value is number | null {
  return value === null || (typeof value === "number" && Number.isFinite(value) && value >= 0);
}

function isNonNegativeNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isNullableNonNegativeInteger(value: unknown): value is number | null {
  return value === null || isNonNegativeInteger(value);
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && Number.isInteger(value) && value >= 0;
}

/* ------------------------------------------------------------------ */
/*  Mock fallback                                                      */
/*                                                                     */
/*  Plausible operational data: anonymised tenant IDs, varied statuses,*/
/*  realistic latencies and token counts. The most-recent failed run   */
/*  is surfaced first so demos render a meaningful trace immediately.  */
/* ------------------------------------------------------------------ */

type MockRun = {
  summary: ApiRunSummary;
  detail: ApiRun;
};

const MOCK_NOW = Date.parse("2026-04-27T16:42:00.000Z");

function isoMinutesAgo(minutes: number): string {
  return new Date(MOCK_NOW - minutes * 60_000).toISOString();
}

function isoSecondsAfter(iso: string, seconds: number): string {
  return new Date(Date.parse(iso) + seconds * 1000).toISOString();
}

const mockRunsRaw: MockRun[] = [
  buildMockTriageFailure(),
  buildMockClaimsSuboptimal(),
  buildMockKycRunning(),
  buildMockProcurementSucceeded(),
  buildMockBillingSucceeded(),
  buildMockRefundSucceeded(),
];

function mockData(
  requestedRunId: string | undefined,
  requestedSpanId: string | undefined,
  generatedAt: number,
  apiState: ApiState,
): OpsCanvasData {
  const summaries = mockRunsRaw.map((run) => run.summary);
  const sorted = [...summaries].sort(
    (a, b) => Date.parse(b.started_at) - Date.parse(a.started_at),
  );
  const runs = sorted.map(toRunRow.bind(null, generatedAt));
  const selectedSummary = chooseSelectedSummary(sorted, requestedRunId);
  const detail =
    selectedSummary === null
      ? null
      : (mockRunsRaw.find((run) => run.summary.id === selectedSummary.id)?.detail ?? null);
  const spans = detail === null ? [] : mapSpans(detail.spans, detail);
  const selectedSpan = chooseSelectedSpan(spans, requestedSpanId);
  const referenceRun: ApiRun | ApiRunSummary | null = detail ?? selectedSummary;
  const totalRunDurationMs =
    referenceRun === null
      ? null
      : durationMsBetween(referenceRun.started_at, referenceRun.ended_at);

  const metrics: MetricsSummary = {
    totalRuns: summaries.length,
    failedRuns: summaries.filter((s) => s.status === "failed").length,
    suboptimalRuns: summaries.filter((s) => s.status === "suboptimal").length,
    runningRuns: summaries.filter((s) => s.status === "running").length,
    totalCostUsd: summaries.reduce((acc, s) => acc + (s.cost_usd ?? 0), 0),
    totalTokens: summaries.reduce((acc, s) => acc + (s.total_tokens ?? 0), 0),
    p95LatencyMs: estimateP95Latency(summaries),
  };

  return {
    apiState,
    runs,
    spans,
    metrics,
    selectedRunId: selectedSummary?.id ?? null,
    selectedRun:
      selectedSummary === null
        ? null
        : (runs.find((row) => row.id === selectedSummary.id) ?? null),
    selectedSpan,
    totalRunDurationMs,
    generatedAt,
  };
}

function estimateP95Latency(summaries: ApiRunSummary[]): number | null {
  const durations = summaries
    .map((summary) => durationMsBetween(summary.started_at, summary.ended_at))
    .filter((value): value is number => value !== null)
    .sort((a, b) => a - b);
  if (durations.length === 0) {
    return null;
  }
  const index = Math.max(0, Math.ceil(0.95 * durations.length) - 1);
  return durations[index];
}

function buildMockTriageFailure(): MockRun {
  const id = "run_8b2af11";
  const started = isoMinutesAgo(7);
  const ended = isoSecondsAfter(started, 18.42);
  const rootId = `${id}_agent`;
  const classifyId = `${id}_classify`;
  const lookupId = `${id}_lookup`;
  const refundId = `${id}_refund`;
  const draftId = `${id}_draft`;

  const detail: ApiRun = {
    id,
    schema_version: "1.0",
    status: "failed",
    started_at: started,
    ended_at: ended,
    runtime: "openai-agents",
    project_id: "project_support",
    environment: "production",
    tenant_id: "tenant_a312",
    user_id: null,
    workflow_name: "support-triage",
    usage: {
      input_tokens: 5240,
      output_tokens: 1280,
      cached_input_tokens: 1920,
      reasoning_tokens: 420,
      total_tokens: 6520,
      cost_usd: 0.4318,
    },
    metadata: { provider: "openai", model: "gpt-5.1" },
    spans: [
      {
        id: rootId,
        run_id: id,
        kind: "agent",
        name: "SupportTriageAgent",
        parent_id: null,
        started_at: started,
        ended_at: ended,
        usage: {
          input_tokens: 5240,
          output_tokens: 1280,
          cached_input_tokens: 1920,
          reasoning_tokens: 420,
          total_tokens: 6520,
          cost_usd: 0.4318,
        },
        input: { ticket_id: "ticket_5188", channel: "email" },
        output: { status: "failed", reason: "downstream tool error" },
        attributes: { "agent.model": "gpt-5.1", retries: 1 },
        events: [
          {
            id: `${rootId}_started`,
            span_id: rootId,
            name: "agent.started",
            timestamp: started,
            attributes: { queue_ms: 38 },
          },
          {
            id: `${rootId}_failed`,
            span_id: rootId,
            name: "agent.failed",
            timestamp: ended,
            attributes: { reason: "tool charge_refund returned 502" },
          },
        ],
      },
      {
        id: classifyId,
        run_id: id,
        kind: "model_call",
        name: "classify_intent",
        parent_id: rootId,
        started_at: isoSecondsAfter(started, 0.32),
        ended_at: isoSecondsAfter(started, 1.92),
        usage: {
          input_tokens: 1860,
          output_tokens: 220,
          cached_input_tokens: 0,
          reasoning_tokens: 0,
          total_tokens: 2080,
          cost_usd: 0.0231,
        },
        input: {
          model: "gpt-5.1-mini",
          messages: [{ role: "user", content: "Classify this ticket." }],
        },
        output: { intent: "refund_request", confidence: 0.94 },
        attributes: { provider: "openai", model: "gpt-5.1-mini", temperature: 0.1 },
        events: [],
      },
      {
        id: lookupId,
        run_id: id,
        kind: "tool_call",
        name: "lookup_account",
        parent_id: rootId,
        started_at: isoSecondsAfter(started, 2.0),
        ended_at: isoSecondsAfter(started, 2.43),
        usage: { input_tokens: 0, output_tokens: 0, cached_input_tokens: 0, reasoning_tokens: 0, total_tokens: 0, cost_usd: 0 },
        input: { tenant_id: "tenant_a312", account_id: "acct_88123" },
        output: { account_status: "active", refund_eligible: true },
        attributes: { tool: "mcp:billing", "http.status_code": 200, latency_ms: 428 },
        events: [
          {
            id: `${lookupId}_done`,
            span_id: lookupId,
            name: "tool.completed",
            timestamp: isoSecondsAfter(started, 2.43),
            attributes: { records: 1 },
          },
        ],
      },
      {
        id: refundId,
        run_id: id,
        kind: "tool_call",
        name: "charge_refund",
        parent_id: rootId,
        started_at: isoSecondsAfter(started, 2.5),
        ended_at: isoSecondsAfter(started, 11.42),
        usage: { input_tokens: 0, output_tokens: 0, cached_input_tokens: 0, reasoning_tokens: 0, total_tokens: 0, cost_usd: 0 },
        input: { account_id: "acct_88123", amount_cents: 4900, idempotency_key: "ref_5188_1" },
        output: null,
        attributes: {
          tool: "mcp:billing",
          "http.status_code": 502,
          "error.message": "upstream payment processor returned 502 Bad Gateway",
          "retry.attempt": 1,
          status: "failed",
        },
        events: [
          {
            id: `${refundId}_started`,
            span_id: refundId,
            name: "tool.started",
            timestamp: isoSecondsAfter(started, 2.5),
            attributes: {},
          },
          {
            id: `${refundId}_retry`,
            span_id: refundId,
            name: "retry.scheduled",
            timestamp: isoSecondsAfter(started, 5.41),
            attributes: { attempt: 1, backoff_ms: 600 },
          },
          {
            id: `${refundId}_error`,
            span_id: refundId,
            name: "tool.error",
            timestamp: isoSecondsAfter(started, 11.42),
            attributes: { code: "upstream_502", message: "payment processor returned 502" },
          },
        ],
      },
      {
        id: draftId,
        run_id: id,
        kind: "model_call",
        name: "draft_apology",
        parent_id: rootId,
        started_at: isoSecondsAfter(started, 11.5),
        ended_at: isoSecondsAfter(started, 18.4),
        usage: {
          input_tokens: 3380,
          output_tokens: 1060,
          cached_input_tokens: 1920,
          reasoning_tokens: 420,
          total_tokens: 4440,
          cost_usd: 0.4087,
        },
        input: {
          model: "gpt-5.1",
          messages: [{ role: "system", content: "Apologize and propose next steps." }],
        },
        output: { summary: "Apology drafted; refund will be retried." },
        attributes: { provider: "openai", model: "gpt-5.1", temperature: 0.3, "interrupted_by": "parent_failed" },
        events: [],
      },
    ],
  };

  return { detail, summary: summaryFromDetail(detail) };
}

function buildMockClaimsSuboptimal(): MockRun {
  const id = "run_3d041ef";
  const started = isoMinutesAgo(22);
  const ended = isoSecondsAfter(started, 11.04);
  const rootId = `${id}_agent`;
  const detail: ApiRun = {
    id,
    schema_version: "1.0",
    status: "suboptimal",
    started_at: started,
    ended_at: ended,
    runtime: "langgraph",
    project_id: "project_claims",
    environment: "production",
    tenant_id: "tenant_b8df",
    user_id: null,
    workflow_name: "claims-classification",
    usage: {
      input_tokens: 3120,
      output_tokens: 740,
      cached_input_tokens: 0,
      reasoning_tokens: 180,
      total_tokens: 3860,
      cost_usd: 0.1182,
    },
    metadata: { provider: "anthropic", model: "claude-3.7-sonnet" },
    spans: [
      {
        id: rootId,
        run_id: id,
        kind: "agent",
        name: "ClaimsTriageGraph",
        parent_id: null,
        started_at: started,
        ended_at: ended,
        usage: {
          input_tokens: 3120,
          output_tokens: 740,
          cached_input_tokens: 0,
          reasoning_tokens: 180,
          total_tokens: 3860,
          cost_usd: 0.1182,
        },
        input: { claim_id: "claim_2241" },
        output: { decision: "needs_review", confidence: 0.62 },
        attributes: {
          "agent.model": "claude-3.7-sonnet",
          "failure.severity": "suboptimal",
          "failure.kind": "low_confidence",
        },
        events: [
          {
            id: `${rootId}_subopt`,
            span_id: rootId,
            name: "quality.suboptimal_detected",
            timestamp: isoSecondsAfter(started, 8.4),
            attributes: { reason: "confidence below 0.7 threshold" },
          },
        ],
      },
    ],
  };
  return { detail, summary: summaryFromDetail(detail) };
}

function buildMockKycRunning(): MockRun {
  const id = "run_f4711a2";
  const started = isoMinutesAgo(2);
  const detail: ApiRun = {
    id,
    schema_version: "1.0",
    status: "running",
    started_at: started,
    ended_at: null,
    runtime: "claude-agent",
    project_id: "project_compliance",
    environment: "production",
    tenant_id: "tenant_e041",
    user_id: null,
    workflow_name: "kyc-document-review",
    usage: { input_tokens: 1820, output_tokens: 0, cached_input_tokens: 512, reasoning_tokens: 0, total_tokens: 1820, cost_usd: 0.0186 },
    metadata: { provider: "anthropic", model: "claude-3.7-sonnet" },
    spans: [
      {
        id: `${id}_agent`,
        run_id: id,
        kind: "agent",
        name: "KycReviewAgent",
        parent_id: null,
        started_at: started,
        ended_at: null,
        usage: { total_tokens: 1820, cost_usd: 0.0186, input_tokens: 1820, output_tokens: 0, cached_input_tokens: 512, reasoning_tokens: 0 },
        input: { document_id: "doc_kyc_91201" },
        output: null,
        attributes: { "agent.model": "claude-3.7-sonnet", status: "running" },
        events: [],
      },
    ],
  };
  return { detail, summary: summaryFromDetail(detail) };
}

function buildMockProcurementSucceeded(): MockRun {
  const id = "run_1c92b88";
  const started = isoMinutesAgo(38);
  const ended = isoSecondsAfter(started, 4.62);
  const detail: ApiRun = {
    id,
    schema_version: "1.0",
    status: "succeeded",
    started_at: started,
    ended_at: ended,
    runtime: "crewai",
    project_id: "project_procurement",
    environment: "production",
    tenant_id: "tenant_a312",
    user_id: null,
    workflow_name: "procurement-routing",
    usage: { input_tokens: 1240, output_tokens: 320, cached_input_tokens: 0, reasoning_tokens: 0, total_tokens: 1560, cost_usd: 0.0214 },
    metadata: { provider: "openai", model: "gpt-5.1-mini" },
    spans: [
      {
        id: `${id}_agent`,
        run_id: id,
        kind: "agent",
        name: "ProcurementRouter",
        parent_id: null,
        started_at: started,
        ended_at: ended,
        usage: { total_tokens: 1560, cost_usd: 0.0214, input_tokens: 1240, output_tokens: 320, cached_input_tokens: 0, reasoning_tokens: 0 },
        input: { request_id: "po_4421" },
        output: { routed_to: "vendor_north", category: "logistics" },
        attributes: { "agent.model": "gpt-5.1-mini" },
        events: [],
      },
    ],
  };
  return { detail, summary: summaryFromDetail(detail) };
}

function buildMockBillingSucceeded(): MockRun {
  const id = "run_77fd219";
  const started = isoMinutesAgo(54);
  const ended = isoSecondsAfter(started, 2.18);
  const detail: ApiRun = {
    id,
    schema_version: "1.0",
    status: "succeeded",
    started_at: started,
    ended_at: ended,
    runtime: "otel",
    project_id: "project_billing",
    environment: "production",
    tenant_id: "tenant_b8df",
    user_id: null,
    workflow_name: "invoice-reconciliation",
    usage: { input_tokens: 820, output_tokens: 140, cached_input_tokens: 320, reasoning_tokens: 0, total_tokens: 960, cost_usd: 0.0091 },
    metadata: { provider: "google", model: "gemini-2.5-pro" },
    spans: [
      {
        id: `${id}_agent`,
        run_id: id,
        kind: "agent",
        name: "InvoiceReconciler",
        parent_id: null,
        started_at: started,
        ended_at: ended,
        usage: { total_tokens: 960, cost_usd: 0.0091, input_tokens: 820, output_tokens: 140, cached_input_tokens: 320, reasoning_tokens: 0 },
        input: { batch_id: "batch_2026_04_27" },
        output: { reconciled: 142, mismatched: 0 },
        attributes: { "agent.model": "gemini-2.5-pro" },
        events: [],
      },
    ],
  };
  return { detail, summary: summaryFromDetail(detail) };
}

function buildMockRefundSucceeded(): MockRun {
  const id = "run_2e08c50";
  const started = isoMinutesAgo(83);
  const ended = isoSecondsAfter(started, 6.74);
  const detail: ApiRun = {
    id,
    schema_version: "1.0",
    status: "succeeded",
    started_at: started,
    ended_at: ended,
    runtime: "openai-agents",
    project_id: "project_support",
    environment: "production",
    tenant_id: "tenant_e041",
    user_id: null,
    workflow_name: "refund-resolution",
    usage: { input_tokens: 2040, output_tokens: 460, cached_input_tokens: 512, reasoning_tokens: 80, total_tokens: 2500, cost_usd: 0.0388 },
    metadata: { provider: "openai", model: "gpt-5.1" },
    spans: [
      {
        id: `${id}_agent`,
        run_id: id,
        kind: "agent",
        name: "RefundResolver",
        parent_id: null,
        started_at: started,
        ended_at: ended,
        usage: { total_tokens: 2500, cost_usd: 0.0388, input_tokens: 2040, output_tokens: 460, cached_input_tokens: 512, reasoning_tokens: 80 },
        input: { ticket_id: "ticket_5142" },
        output: { refund_id: "ref_991", amount_cents: 2400 },
        attributes: { "agent.model": "gpt-5.1" },
        events: [],
      },
    ],
  };
  return { detail, summary: summaryFromDetail(detail) };
}

function summaryFromDetail(run: ApiRun): ApiRunSummary {
  return {
    id: run.id,
    schema_version: run.schema_version,
    status: run.status,
    runtime: run.runtime,
    started_at: run.started_at,
    ended_at: run.ended_at,
    tenant_id: run.tenant_id,
    environment: run.environment,
    workflow_name: run.workflow_name,
    span_count: run.spans.length,
    event_count: run.spans.reduce((acc, span) => acc + span.events.length, 0),
    cost_usd: run.usage?.cost_usd ?? null,
    total_tokens: run.usage?.total_tokens ?? null,
  };
}
