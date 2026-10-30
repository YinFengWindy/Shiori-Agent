import { CalendarDots, CaretRight, Plus } from "@phosphor-icons/react";
import { compactIconButtonClass, cx, sidebarNavItemClass, type PluginHostServices } from "@yinfengwindy/shiori-sdk";
import type { ScheduledTask } from "./types";

/** The role's scheduled tasks as one group of the panel's task list. */
export function ScheduleTaskGroup({ tasks, error, host, onCreate, onSelect }: {
  tasks: ScheduledTask[];
  error: string;
  host: PluginHostServices;
  onCreate: () => void;
  onSelect: (taskId: string) => void;
}) {
  const { InlineError } = host.ui;
  return (
    <section data-testid="schedule-task-group" className="rounded-md p-2">
      <div className="flex items-center gap-1.5 px-1 pb-2 text-[11px] font-medium tracking-wide text-ink-muted">
        <CalendarDots className="h-3.5 w-3.5" weight="fill" />
        <span>计划任务</span>
        <span className="ml-auto grid min-h-5 min-w-5 place-items-center rounded-md bg-surface-soft px-1 text-[10px] text-ink-muted">{tasks.length}</span>
        <button className={compactIconButtonClass} type="button" aria-label="新增计划任务" onClick={onCreate}>
          <Plus className="h-4 w-4" weight="bold" />
        </button>
      </div>
      {error ? <InlineError message={error} /> : null}
      {tasks.map((task) => (
        <button
          key={task.id}
          className={cx(sidebarNavItemClass, "group grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-2 px-2.5 py-2.5 text-left")}
          type="button"
          onClick={() => onSelect(task.id)}
        >
          <span className="min-w-0">
            <span className="block truncate text-[13px] font-semibold text-ink-secondary">{task.label}</span>
            <span className="mt-1 block truncate text-[11px] text-ink-muted">{task.detail || "—"}</span>
          </span>
          <CaretRight className="h-3.5 w-3.5 text-ink-faint transition-colors group-hover:text-ink-muted" />
        </button>
      ))}
    </section>
  );
}
