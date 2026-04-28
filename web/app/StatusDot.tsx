import type { ApiRunStatus } from "./data";

type Props = {
  status: ApiRunStatus;
  label?: string;
  decorative?: boolean;
};

export function StatusDot({ status, label, decorative = false }: Props) {
  return (
    <span
      className={`status-dot s-${status}`}
      role={decorative ? undefined : "img"}
      aria-hidden={decorative ? "true" : undefined}
      aria-label={decorative ? undefined : (label ?? status)}
    />
  );
}

export function StatusLabel({ status }: { status: ApiRunStatus }) {
  return (
    <span className={`status-label s-${status}`}>
      <StatusDot status={status} decorative />
      {status}
    </span>
  );
}
