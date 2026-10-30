import { CalendarDots, CaretRight, Plus } from "@phosphor-icons/react";
import {
  compactIconButtonClass,
  roleTaskGroupCountClass,
  roleTaskGroupHeadClass,
  roleTaskRowClass,
  roleTaskRowSummaryClass,
  roleTaskRowTitleClass,
  type PluginHostServices,
} from "@yinfengwindy/shiori-sdk";
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
      <div className={roleTaskGroupHeadClass}>
        <CalendarDots className="h-3.5 w-3.5" weight="fill" />
        <span>计划任务</span>
        <span className={roleTaskGroupCountClass}>{tasks.length}</span>
        <button className={compactIconButtonClass} type="button" aria-label="新增计划任务" onClick={onCreate}>
          <Plus className="h-4 w-4" weight="bold" />
        </button>
      </div>
      {error ? <InlineError message={error} /> : null}
      {tasks.map((task) => (
        <button
          key={task.id}
          className={roleTaskRowClass}
          type="button"
          onClick={() => onSelect(task.id)}
        >
          <span className="min-w-0">
            <span className={roleTaskRowTitleClass}>{task.label}</span>
            <span className={roleTaskRowSummaryClass}>{task.detail || "—"}</span>
          </span>
          <CaretRight className="h-3.5 w-3.5 text-ink-faint transition-colors group-hover:text-ink-muted" />
        </button>
      ))}
    </section>
  );
}
