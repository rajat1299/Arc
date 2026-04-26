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
  depth: number;
  name: string;
  kind: string;
  runtime: string;
  status: DisplayStatus;
  duration: string;
  cost: string;
  offset: number;
  width: number;
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
};

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
    depth: 0,
    name: "RefundResolutionAgent",
    kind: "agent",
    runtime: "openai-agents",
    status: "failed",
    duration: "18.42s",
    cost: "$0.43",
    offset: 0,
    width: 100,
  },
  {
    depth: 1,
    name: "classify_request",
    kind: "model_call",
    runtime: "gpt-4.1-mini",
    status: "succeeded",
    duration: "1.92s",
    cost: "$0.03",
    offset: 4,
    width: 11,
  },
  {
    depth: 1,
    name: "lookup_order",
    kind: "tool_call",
    runtime: "mcp:orders",
    status: "succeeded",
    duration: "428ms",
    cost: "$0.00",
    offset: 17,
    width: 4,
  },
  {
    depth: 1,
    name: "refund_policy_handoff",
    kind: "handoff",
    runtime: "langgraph",
    status: "suboptimal",
    duration: "5.31s",
    cost: "$0.12",
    offset: 23,
    width: 29,
  },
  {
    depth: 2,
    name: "currency_convert",
    kind: "tool_call",
    runtime: "mcp:finance",
    status: "failed",
    duration: "3.84s",
    cost: "$0.01",
    offset: 42,
    width: 20,
  },
  {
    depth: 1,
    name: "draft_customer_reply",
    kind: "model_call",
    runtime: "gpt-4.1",
    status: "succeeded",
    duration: "6.88s",
    cost: "$0.27",
    offset: 60,
    width: 37,
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
};

export async function getOpsCanvasData(): Promise<OpsCanvasData> {
  const apiRuns = await fetchRunSummaries();

  if (apiRuns === null) {
    return mockData;
  }

  return {
    ...mockData,
    runs: apiRuns.map(mapRunSummaryToRun),
  };
}

export async function fetchRunSummaries(): Promise<ApiRunSummary[] | null> {
  const baseUrl = process.env.OPSCANVAS_API_BASE_URL?.trim();

  if (!baseUrl) {
    return null;
  }

  try {
    const response = await fetch(new URL("/v1/runs", baseUrl), {
      cache: "no-store",
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
  }
}

function mapRunSummaryToRun(run: ApiRunSummary): Run {
  return {
    id: run.id,
    name: run.workflow_name ?? run.id,
    tenant: run.tenant_id ?? "unknown",
    runtime: run.runtime,
    model: run.environment ?? "n/a",
    status: run.status,
    duration: formatDuration(run.started_at, run.ended_at, run.status),
    cost: formatCost(run.cost_usd),
    tokens: formatTokens(run.total_tokens),
    started: formatStartedAt(run.started_at),
  };
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
    typeof value.span_count === "number" &&
    typeof value.event_count === "number" &&
    (typeof value.cost_usd === "number" || value.cost_usd === null) &&
    (typeof value.total_tokens === "number" || value.total_tokens === null)
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
