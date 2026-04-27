import type { ApiRunStatus } from "./data";

type Props = {
  status: ApiRunStatus;
  label?: string;
};

export function StatusDot({ status, label }: Props) {
  return (
    <span
      className={`status-dot s-${status}`}
      role={label ? undefined : "img"}
      aria-label={label ?? status}
    />
  );
}

export function StatusLabel({ status }: { status: ApiRunStatus }) {
  return (
    <span className={`status-label s-${status}`}>
      <StatusDot status={status} />
      {status}
    </span>
  );
}
