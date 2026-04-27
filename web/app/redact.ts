/**
 * Defense-in-depth secret redaction for span attributes/inputs/outputs
 * before they hit the DOM. The backend already redacts at the edge; this is
 * an additional client-render-time filter so the rendered JSON never carries
 * an obvious bearer token, API key, or password value.
 *
 * Redaction is *display-only*. Originals are never persisted in the UI layer.
 */

const REDACTED = "[redacted]";
const MAX_DEPTH = 8;

const SECRET_KEY_PATTERN =
  /^(authorization|auth|api[_-]?key|apikey|secret|password|passwd|pwd|access[_-]?token|refresh[_-]?token|bearer|x-api-key|cookie|set-cookie)$/i;

const SECRET_VALUE_PATTERNS: ReadonlyArray<RegExp> = [
  /Bearer\s+[A-Za-z0-9._\-+/=]{8,}/g,
  /\bsk-(?:proj-|ant-|[A-Za-z0-9_\-]{0,8})?[A-Za-z0-9_\-]{20,}\b/g,
  /\bxox[abprs]-[A-Za-z0-9-]{10,}\b/g,
  /\bAKIA[0-9A-Z]{16}\b/g,
  /\bgh[pousr]_[A-Za-z0-9]{16,}\b/g,
];

export function redactValue(value: unknown, depth: number = 0): unknown {
  if (depth > MAX_DEPTH) {
    return REDACTED;
  }

  if (value === null || value === undefined) {
    return value;
  }

  if (typeof value === "string") {
    return redactString(value);
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return value;
  }

  if (Array.isArray(value)) {
    return value.map((item) => redactValue(item, depth + 1));
  }

  if (typeof value === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(value)) {
      if (SECRET_KEY_PATTERN.test(key)) {
        result[key] = REDACTED;
        continue;
      }
      result[key] = redactValue(child, depth + 1);
    }
    return result;
  }

  return value;
}

export function redactRecord(value: Record<string, unknown>): Record<string, unknown> {
  return redactValue(value, 0) as Record<string, unknown>;
}

function redactString(value: string): string {
  let out = value;
  for (const pattern of SECRET_VALUE_PATTERNS) {
    out = out.replace(pattern, REDACTED);
  }
  return out;
}
