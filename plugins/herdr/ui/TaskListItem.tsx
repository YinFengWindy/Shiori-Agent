import { cx, sidebarNavItemClass, type PluginHostServices, type RoleRecord } from "@yinfengwindy/shiori-sdk";
import { RoleAvatar } from "./RoleAvatar";
import { AgentStatusLabel } from "./AgentStatusLabel";
import { StatusDot } from "./TaskStatus";
import { phaseLabel, relativeTime, taskTitle } from "./taskSelectors";
import type { AgentSummary, TaskSummary } from "./types";

/** A sidebar row laid out like a chat list row: a 32px leading mark, then two lines. */
export const listItemClass = cx(
  sidebarNavItemClass,
  "grid min-h-[54px] w-full grid-cols-[32px_minmax(0,1fr)] items-center gap-2.5 px-2 py-2 text-left text-body-sm leading-none text-ink-secondary",
);

/** One task row, laid out like a chat list row; a task's listed agent adds its Herdr state. */
export function TaskListItem({ task, agent, role, selected, now, host, onSelect }: {
  task: TaskSummary;
  agent?: AgentSummary;
  role: RoleRecord | undefined;
  selected: boolean;
  now: Date;
  host: PluginHostServices;
  onSelect: (taskId: string) => void;
}) {
  // Reported activity, not the monitor's synchronization heartbeat (`updated_at`).
  const time = relativeTime(task.progress_updated_at || task.created_at, now);
  return (
    <button
      type="button"
      className={cx(listItemClass, selected && "bg-surface text-ink shadow-soft")}
      aria-current={selected ? "true" : undefined}
      onClick={() => onSelect(task.id)}
    >
      <RoleAvatar role={role} host={host} />
      <span className="grid min-w-0 gap-1">
        <span className="flex min-w-0 items-baseline gap-2">
          <span className="min-w-0 truncate font-semibold leading-tight">{taskTitle(task)}</span>
          {time ? <span className="ml-auto flex-none text-caption leading-none tabular-nums text-ink-muted">{time}</span> : null}
        </span>
        <span className="flex min-w-0 items-center gap-1.5 text-caption leading-tight text-ink-muted">
          <StatusDot status={task.status} />
          <span className="truncate">{phaseLabel(task)}</span>
          {agent ? <AgentStatusLabel status={agent.status} /> : null}
        </span>
      </span>
    </button>
  );
}
