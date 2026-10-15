import { cx } from "@yinfengwindy/shiori-sdk";
import { statusLabels, statusTone, type StatusTone } from "./taskSelectors";
import type { TaskStatus } from "./types";

const dotClasses: Record<StatusTone, string> = {
  accent: "bg-accent",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  muted: "bg-line-strong",
};

/** Small colored dot of a task status. */
export function StatusDot({ status }: { status: TaskStatus }) {
  return <span className={cx("h-2 w-2 shrink-0 rounded-full", dotClasses[statusTone(status)])} aria-hidden="true" />;
}

/** Status dot followed by its label. */
export function StatusLabel({ status, className }: { status: TaskStatus; className?: string }) {
  return (
    <span className={cx("inline-flex shrink-0 items-center gap-1.5", className)}>
      <StatusDot status={status} />
      {statusLabels[status]}
    </span>
  );
}
