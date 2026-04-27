/**
 * Formatting primitives for numeric data. All output is intended to render in
 * a monospace, tabular-nums column. Format choices are deliberately
 * single-style per dimension so digit columns line up cleanly:
 *
 *   - cost:      "$0.0642" (small) | "$1.42" | "$18,420"
 *   - duration:  "420ms"   | "1.42s"  | "1m 24s"
 *   - tokens:    "4,280"   | "4.28k"  | "1.92M"
 *   - relative:  "just now" | "3m ago" | "2h ago" | "4d ago"
 */

export function formatCostUSD(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (!Number.isFinite(value)) {
    return "—";
  }
  if (value === 0) {
    return "$0.00";
  }
  if (value < 0.01) {
    return `$${value.toFixed(4)}`;
  }
  if (value < 1) {
    return `$${value.toFixed(3)}`;
  }
  if (value < 1000) {
    return `$${value.toFixed(2)}`;
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatDurationMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) {
    return "—";
  }
  if (ms < 1000) {
    return `${Math.round(ms)}ms`;
  }
  if (ms < 60_000) {
    return `${(ms / 1000).toFixed(2)}s`;
  }
  const totalSeconds = Math.round(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) {
    return `${minutes}m ${seconds.toString().padStart(2, "0")}s`;
  }
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours}h ${mins.toString().padStart(2, "0")}m`;
}

export function formatTokens(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value) || value < 0) {
    return "—";
  }
  if (value < 1000) {
    return value.toString();
  }
  if (value < 100_000) {
    return `${(value / 1000).toFixed(2)}k`;
  }
  if (value < 1_000_000) {
    return `${(value / 1000).toFixed(1)}k`;
  }
  return `${(value / 1_000_000).toFixed(2)}M`;
}

/**
 * Stable, locale-independent relative time string. Computed on the server and
 * sent down in the rendered HTML so we don't introduce hydration mismatches.
 * Caller is responsible for choosing the comparison "now" — usually
 * `Date.now()` at request time.
 */
export function formatRelativeTime(value: Date | string | null | undefined, now: number): string {
  if (value === null || value === undefined) {
    return "—";
  }
  const time = value instanceof Date ? value.getTime() : Date.parse(value);
  if (!Number.isFinite(time)) {
    return "—";
  }

  const diffMs = now - time;
  if (diffMs < 0) {
    return "just now";
  }
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 30) {
    return "just now";
  }
  if (seconds < 60) {
    return `${seconds}s ago`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  if (days < 7) {
    return `${days}d ago`;
  }
  const weeks = Math.floor(days / 7);
  if (weeks < 5) {
    return `${weeks}w ago`;
  }
  const months = Math.floor(days / 30);
  if (months < 12) {
    return `${months}mo ago`;
  }
  const years = Math.floor(days / 365);
  return `${years}y ago`;
}

/**
 * Compute duration in milliseconds from canonical ISO timestamps.
 * Returns null when either timestamp is missing or invalid.
 */
export function durationMsBetween(
  startedAt: string | null | undefined,
  endedAt: string | null | undefined,
): number | null {
  if (!startedAt || !endedAt) {
    return null;
  }
  const started = Date.parse(startedAt);
  const ended = Date.parse(endedAt);
  if (!Number.isFinite(started) || !Number.isFinite(ended) || ended < started) {
    return null;
  }
  return ended - started;
}

/**
 * Render an event timestamp as `+0.230s` relative to a span start.
 * Used in the events timeline.
 */
export function formatEventOffset(
  eventTimestamp: string | null | undefined,
  spanStartedAt: string | null | undefined,
): string {
  if (!eventTimestamp || !spanStartedAt) {
    return "+0.000s";
  }
  const event = Date.parse(eventTimestamp);
  const start = Date.parse(spanStartedAt);
  if (!Number.isFinite(event) || !Number.isFinite(start) || event < start) {
    return "+0.000s";
  }
  return `+${((event - start) / 1000).toFixed(3)}s`;
}
