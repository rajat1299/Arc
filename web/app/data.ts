export type ApiRunStatus = "succeeded" | "failed" | "interrupted" | "suboptimal" | "running";

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
  kind:
    | "agent"
    | "model_call"
    | "tool_call"
    | "handoff"
    | "guardrail"
    | "mcp_list"
    | "sandbox_op"
    | "retry"
    | "custom";
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

export type ApiRunMetrics = {
  run_count: number;
  failed_count: number;
  running_count: number;
  suboptimal_count: number;
  total_cost_usd: number;
  total_tokens: number;
  p95_latency_ms: number | null;
};

export type DisplayStatus = ApiRunStatus;

export type Run = {
  id: string;
  name: string;
  tenant: string;
  runtime: string;
  model: string;
  status: DisplayStatus;
  duration: string;
  cost: string;
  tokens: string;
  started: string;
};

export type Span = {
  id: string;
  parentId: string | null;
  depth: number;
  name: string;
  kind: string;
  runtime: string;
  status: DisplayStatus;
  duration: string;
  cost: string;
  offset: number;
  width: number;
  events: SpanEvent[];
};

export type SpanEvent = {
  id: string;
  name: string;
  timestamp: string;
  offset: string;
};

export type SummaryMetric = {
  label: string;
  value: string;
  delta: string;
};

export type OpsCanvasData = {
  runs: Run[];
  spans: Span[];
  summary: SummaryMetric[];
  selectedRunId: string;
  selectedRun: Run;
  selectedSpan: Span;
  totalDuration: string;
};

const RUNS_FETCH_TIMEOUT_MS = 1500;
const DETAIL_FETCH_TIMEOUT_MS = 1500;

const mockRuns: Run[] = [
  {
    id: "run_7f91c2",
    name: "refund-resolution",
    tenant: "northstar",
    runtime: "openai-agents",
    model: "gpt-4.1",
    status: "failed",
    duration: "18.42s",
    cost: "$0.43",
    tokens: "42.8k",
    started: "09:41:22",
  },
  {
    id: "run_42be19",
    name: "claims-triage",
    tenant: "apex",
    runtime: "langgraph",
    model: "claude-3.7",
    status: "running",
    duration: "31.08s",
    cost: "$0.71",
    tokens: "64.1k",
    started: "09:39:04",
  },
  {
    id: "run_b803ab",
    name: "renewal-router",
    tenant: "evergreen",
    runtime: "crewai",
    model: "gpt-4.1-mini",
    status: "suboptimal",
    duration: "09.77s",
    cost: "$0.08",
    tokens: "12.4k",
    started: "09:36:48",
  },
  {
    id: "run_31a64d",
    name: "policy-audit",
    tenant: "northstar",
    runtime: "otel",
    model: "gemini-2.5",
    status: "succeeded",
    duration: "06.12s",
    cost: "$0.05",
    tokens: "7.9k",
    started: "09:34:10",
  },
];

const mockSpans: Span[] = [
  {
    id: "span_refund_resolution",
    parentId: null,
    depth: 0,
    name: "RefundResolutionAgent",
    kind: "agent",
    runtime: "openai-agents",
    status: "failed",
    duration: "18.42s",
    cost: "$0.43",
    offset: 0,
    width: 100,
    events: [
      { id: "event_refund_started", name: "run.started", timestamp: "", offset: "+0.000s" },
      { id: "event_refund_failed", name: "run.failed", timestamp: "", offset: "+18.420s" },
    ],
  },
  {
    id: "span_classify_request",
    parentId: "span_refund_resolution",
    depth: 1,
    name: "classify_request",
    kind: "model_call",
    runtime: "gpt-4.1-mini",
    status: "succeeded",
    duration: "1.92s",
    cost: "$0.03",
    offset: 4,
    width: 11,
    events: [{ id: "event_classify_done", name: "model.completed", timestamp: "", offset: "+1.920s" }],
  },
  {
    id: "span_lookup_order",
    parentId: "span_refund_resolution",
    depth: 1,
    name: "lookup_order",
    kind: "tool_call",
    runtime: "mcp:orders",
    status: "succeeded",
    duration: "428ms",
    cost: "$0.00",
    offset: 17,
    width: 4,
    events: [{ id: "event_lookup_done", name: "tool.completed", timestamp: "", offset: "+0.428s" }],
  },
  {
    id: "span_refund_policy_handoff",
    parentId: "span_refund_resolution",
    depth: 1,
    name: "refund_policy_handoff",
    kind: "handoff",
    runtime: "langgraph",
    status: "suboptimal",
    duration: "5.31s",
    cost: "$0.12",
    offset: 23,
    width: 29,
    events: [{ id: "event_handoff_warn", name: "handoff.suboptimal", timestamp: "", offset: "+5.310s" }],
  },
  {
    id: "span_currency_convert",
    parentId: "span_refund_policy_handoff",
    depth: 2,
    name: "currency_convert",
    kind: "tool_call",
    runtime: "mcp:finance",
    status: "failed",
    duration: "3.84s",
    cost: "$0.01",
    offset: 42,
    width: 20,
    events: [
      { id: "event_currency_started", name: "request.started", timestamp: "", offset: "+2.101s" },
      { id: "event_currency_retry", name: "retry.scheduled", timestamp: "", offset: "+4.903s" },
      { id: "event_currency_error", name: "tool.error", timestamp: "", offset: "+5.941s" },
    ],
  },
  {
    id: "span_draft_customer_reply",
    parentId: "span_refund_resolution",
    depth: 1,
    name: "draft_customer_reply",
    kind: "model_call",
    runtime: "gpt-4.1",
    status: "succeeded",
    duration: "6.88s",
    cost: "$0.27",
    offset: 60,
    width: 37,
    events: [{ id: "event_draft_done", name: "model.completed", timestamp: "", offset: "+6.880s" }],
  },
];

const mockSummary: SummaryMetric[] = [
  { label: "MTD spend", value: "$18,420", delta: "+12.4%" },
  { label: "p95 latency", value: "24.8s", delta: "+3.1s" },
  { label: "eval pass rate", value: "91.6%", delta: "-2.8%" },
  { label: "failed runs", value: "43", delta: "+9" },
];

export const mockData: OpsCanvasData = {
  runs: mockRuns,
  spans: mockSpans,
  summary: mockSummary,
  selectedRunId: mockRuns[0].id,
  selectedRun: mockRuns[0],
  selectedSpan: mockSpans.find((span) => span.status === "failed") ?? mockSpans[0],
  totalDuration: mockRuns[0].duration,
};

export async function getOpsCanvasData(selectedRunId?: string): Promise<OpsCanvasData> {
  const apiRuns = await fetchRunSummaries();

  if (apiRuns === null) {
    return selectMockData(selectedRunId);
  }

  const activeSummary = apiRuns.find((run) => run.id === selectedRunId) ?? apiRuns[0];

  if (activeSummary === undefined) {
    return {
      ...mockData,
      runs: [],
    };
  }

  const [apiRun, apiSpans, apiMetrics] = await Promise.all([
    fetchRun(activeSummary.id),
    fetchRunSpans(activeSummary.id),
    fetchRunMetrics(),
  ]);
  const runs = orderSelectedRunFirst(
    apiRuns.map((run) => mapRunSummaryToRun(run, apiRun?.id === run.id ? apiRun : undefined)),
    activeSummary.id,
  );
  const selectedRun = runs.find((run) => run.id === activeSummary.id) ?? mapRunSummaryToRun(activeSummary, apiRun ?? undefined);
  const spans = apiSpans === null ? mockSpans : mapSpans(apiSpans, apiRun ?? activeSummary);

  return {
    ...mockData,
    runs,
    spans,
    summary: apiMetrics === null ? mockSummary : mapRunMetricsToSummary(apiMetrics),
    selectedRunId: selectedRun.id,
    selectedRun,
    selectedSpan: chooseSelectedSpan(spans),
    totalDuration: selectedRun.duration,
  };
}

export async function fetchRunSummaries(): Promise<ApiRunSummary[] | null> {
  const baseUrl = process.env.OPSCANVAS_API_BASE_URL?.trim();

  if (!baseUrl) {
    return null;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), RUNS_FETCH_TIMEOUT_MS);

  try {
    const response = await fetch(new URL("/v1/runs", baseUrl), {
      cache: "no-store",
      signal: controller.signal,
    });

    if (!response.ok) {
      return null;
    }

    const payload: unknown = await response.json();

    if (!Array.isArray(payload)) {
      return null;
    }

    if (!payload.every(isApiRunSummary)) {
      return null;
    }

    return payload;
  } catch {
    return null;
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchRun(runId: string): Promise<ApiRun | null> {
  return fetchApiJson(`/v1/runs/${encodeURIComponent(runId)}`, isApiRun);
}

async function fetchRunSpans(runId: string): Promise<ApiSpan[] | null> {
  return fetchApiJson(`/v1/runs/${encodeURIComponent(runId)}/spans`, isApiSpanList);
}

async function fetchRunMetrics(): Promise<ApiRunMetrics | null> {
  return fetchApiJson("/v1/runs/metrics", isApiRunMetrics);
}

async function fetchApiJson<T>(path: string, validate: (payload: unknown) => payload is T): Promise<T | null> {
  const baseUrl = process.env.OPSCANVAS_API_BASE_URL?.trim();

  if (!baseUrl) {
    return null;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DETAIL_FETCH_TIMEOUT_MS);

  try {
    const response = await fetch(new URL(path, baseUrl), {
      cache: "no-store",
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

function mapRunSummaryToRun(run: ApiRunSummary, detail?: ApiRun): Run {
  const usage = detail?.usage;
  const metadata = detail?.metadata;
  const model = firstString(metadata?.model, metadata?.model_name, metadata?.provider_model, detail?.environment, run.environment, "n/a");

  return {
    id: run.id,
    name: detail?.workflow_name ?? run.workflow_name ?? run.id,
    tenant: detail?.tenant_id ?? run.tenant_id ?? "unknown",
    runtime: detail?.runtime ?? run.runtime,
    model,
    status: run.status,
    duration: formatDuration(detail?.started_at ?? run.started_at, detail?.ended_at ?? run.ended_at, run.status),
    cost: formatCost(usage?.cost_usd ?? run.cost_usd),
    tokens: formatTokens(usage?.total_tokens ?? run.total_tokens),
    started: formatStartedAt(detail?.started_at ?? run.started_at),
  };
}

function mapSpans(spans: ApiSpan[], run: ApiRun | ApiRunSummary): Span[] {
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
    const offset = started === null ? 0 : clampPercent(((started - timelineStart) / timelineMs) * 100);
    const width =
      started === null || ended === null || ended < started
        ? 4
        : Math.max(3, clampPercent(((ended - started) / timelineMs) * 100));

    return {
      id: span.id,
      parentId: span.parent_id,
      depth,
      name: span.name,
      kind: span.kind,
      runtime: spanRuntime(span),
      status: spanStatus(span, run.status),
      duration: formatDuration(span.started_at, span.ended_at, run.status),
      cost: formatCost(span.usage?.cost_usd ?? null),
      offset,
      width: Math.min(width, 100 - offset),
      events: span.events.map((event) => ({
        id: event.id,
        name: event.name,
        timestamp: event.timestamp,
        offset: formatEventOffset(event.timestamp, span.started_at),
      })),
    };
  });
}

function mapRunMetricsToSummary(metrics: ApiRunMetrics): SummaryMetric[] {
  return [
    { label: "Total spend", value: formatCost(metrics.total_cost_usd), delta: `${formatTokens(metrics.total_tokens)} tokens` },
    { label: "p95 latency", value: formatMilliseconds(metrics.p95_latency_ms), delta: `${metrics.running_count} running` },
    { label: "Suboptimal runs", value: String(metrics.suboptimal_count), delta: formatPercent(metrics.suboptimal_count, metrics.run_count) },
    { label: "Failed runs", value: String(metrics.failed_count), delta: formatPercent(metrics.failed_count, metrics.run_count) },
  ];
}

function selectMockData(selectedRunId?: string): OpsCanvasData {
  const selectedRun = mockRuns.find((run) => run.id === selectedRunId) ?? mockRuns[0];

  return {
    ...mockData,
    runs: orderSelectedRunFirst(mockRuns, selectedRun.id),
    selectedRunId: selectedRun.id,
    selectedRun,
    totalDuration: selectedRun.duration,
  };
}

function orderSelectedRunFirst(runs: Run[], selectedRunId: string): Run[] {
  const selectedRun = runs.find((run) => run.id === selectedRunId);

  if (selectedRun === undefined) {
    return runs;
  }

  return [selectedRun, ...runs.filter((run) => run.id !== selectedRun.id)];
}

function chooseSelectedSpan(spans: Span[]): Span {
  return (
    spans.find((span) => span.status === "failed") ??
    spans.find((span) => span.status === "suboptimal" || span.status === "interrupted") ??
    spans.find((span) => span.parentId === null) ??
    spans[0] ??
    mockData.selectedSpan
  );
}

function formatDuration(startedAt: string, endedAt: string | null, status: ApiRunStatus): string {
  if (endedAt === null) {
    return status === "running" ? "running" : "n/a";
  }

  const started = Date.parse(startedAt);
  const ended = Date.parse(endedAt);

  if (Number.isNaN(started) || Number.isNaN(ended) || ended < started) {
    return "n/a";
  }

  const seconds = (ended - started) / 1000;
  return `${seconds.toFixed(2)}s`;
}

function formatCost(costUsd: number | null): string {
  if (costUsd === null) {
    return "$0.00";
  }

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: costUsd < 1 ? 2 : 0,
    maximumFractionDigits: costUsd < 1 ? 2 : 0,
  }).format(costUsd);
}

function formatTokens(totalTokens: number | null): string {
  if (totalTokens === null) {
    return "0";
  }

  if (totalTokens >= 1000) {
    return `${(totalTokens / 1000).toFixed(1)}k`;
  }

  return String(totalTokens);
}

function formatMilliseconds(ms: number | null): string {
  if (ms === null) {
    return "n/a";
  }

  if (ms >= 1000) {
    return `${(ms / 1000).toFixed(2)}s`;
  }

  return `${ms}ms`;
}

function formatPercent(count: number, total: number): string {
  if (total === 0) {
    return "0.0%";
  }

  return `${((count / total) * 100).toFixed(1)}%`;
}

function formatStartedAt(startedAt: string): string {
  const started = new Date(startedAt);

  if (Number.isNaN(started.getTime())) {
    return "n/a";
  }

  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(started);
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

function isApiSpanList(value: unknown): value is ApiSpan[] {
  return Array.isArray(value) && value.every(isApiSpan);
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

function isApiSpanKind(value: unknown): value is ApiSpan["kind"] {
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

function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.length > 0) {
      return value;
    }
  }

  return "n/a";
}

function spanRuntime(span: ApiSpan): string {
  return firstString(span.attributes.runtime, span.attributes.model, span.attributes.tool, span.attributes.provider, span.kind);
}

function spanStatus(span: ApiSpan, runStatus: ApiRunStatus): DisplayStatus {
  const status = span.attributes.status;

  if (isApiRunStatus(status)) {
    return status;
  }

  if (span.events.some((event) => event.name.includes("error") || event.name.includes("failed"))) {
    return "failed";
  }

  return runStatus === "failed" && span.parent_id === null ? "failed" : "succeeded";
}

function getSpanDepth(span: ApiSpan, spanById: Map<string, ApiSpan>, depthById: Map<string, number>): number {
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
  return Number.isNaN(parsed) ? null : parsed;
}

function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, value));
}

function formatEventOffset(eventTimestamp: string, spanStartedAt: string): string {
  const eventTime = parseTime(eventTimestamp);
  const spanStarted = parseTime(spanStartedAt);

  if (eventTime === null || spanStarted === null || eventTime < spanStarted) {
    return "+0.000s";
  }

  return `+${((eventTime - spanStarted) / 1000).toFixed(3)}s`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
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
