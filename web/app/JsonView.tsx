import type { ReactNode } from "react";

/**
 * Server-renderable JSON viewer with key/string/number/bool/null coloring.
 *
 * The input is already passed through redact.ts on the data layer, so we
 * render whatever we get without re-redacting. Long string values are
 * truncated in-place so the DOM never balloons; the original is dropped on
 * the floor — fine, since the viewer is read-only.
 */

type Props = {
  value: unknown;
  maxStringLength?: number;
};

const DEFAULT_MAX_STRING = 320;

export function JsonView({ value, maxStringLength = DEFAULT_MAX_STRING }: Props) {
  if (value === null || value === undefined) {
    return <pre className="json-block">null</pre>;
  }

  const truncated = truncateLongStrings(value, maxStringLength);
  const text = JSON.stringify(truncated, null, 2);
  if (text === undefined) {
    return <pre className="json-block">{String(value)}</pre>;
  }

  return <pre className="json-block">{tokenize(text)}</pre>;
}

function tokenize(source: string): ReactNode[] {
  // Match in this order so longer/more-specific patterns win:
  //   1. "key":           a quoted string immediately followed by `:`
  //   2. "string"         any other quoted string (a value)
  //   3. number           int or float (no leading +)
  //   4. true | false | null
  // Anything not matching falls through as plain text.
  const pattern =
    /("(?:[^"\\]|\\.)*")(\s*:)|("(?:[^"\\]|\\.)*")|(-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+\-]?\d+)?)|\b(true|false|null)\b/g;

  const out: ReactNode[] = [];
  let lastIndex = 0;
  let key = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(source)) !== null) {
    if (match.index > lastIndex) {
      out.push(source.slice(lastIndex, match.index));
    }

    if (match[1] !== undefined) {
      // "key":
      out.push(
        <span className="json-key" key={key++}>
          {match[1]}
        </span>,
      );
      out.push(match[2]);
    } else if (match[3] !== undefined) {
      out.push(
        <span className="json-string" key={key++}>
          {match[3]}
        </span>,
      );
    } else if (match[4] !== undefined) {
      out.push(
        <span className="json-number" key={key++}>
          {match[4]}
        </span>,
      );
    } else if (match[5] !== undefined) {
      const className = match[5] === "null" ? "json-null" : "json-bool";
      out.push(
        <span className={className} key={key++}>
          {match[5]}
        </span>,
      );
    }

    lastIndex = pattern.lastIndex;
  }

  if (lastIndex < source.length) {
    out.push(source.slice(lastIndex));
  }

  return out;
}

function truncateLongStrings(value: unknown, max: number): unknown {
  if (typeof value === "string") {
    if (value.length <= max) {
      return value;
    }
    return `${value.slice(0, max)}… (truncated, ${value.length - max} chars)`;
  }

  if (Array.isArray(value)) {
    return value.map((item) => truncateLongStrings(item, max));
  }

  if (value !== null && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, child] of Object.entries(value)) {
      out[key] = truncateLongStrings(child, max);
    }
    return out;
  }

  return value;
}
