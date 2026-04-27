/**
 * Build URLs for run/span deep-linking.
 *
 * Selecting a run clears any previous spanId so the new run defaults to its
 * own failed/root span. Selecting a span keeps the current run.
 */

export function runHref(runId: string): string {
  return `/?runId=${encodeURIComponent(runId)}`;
}

export function spanHref(runId: string, spanId: string): string {
  return `/?runId=${encodeURIComponent(runId)}&spanId=${encodeURIComponent(spanId)}`;
}
