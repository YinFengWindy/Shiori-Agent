import { Brain, CalendarDots, CaretRight, Plus, Robot } from "@phosphor-icons/react";
import type { RoleTask } from "../shared/types";
import { cx } from "@shiori/sdk";
import { focusResetClass } from "../shared/styles";
import { groupRoleTasks, taskKindLabels } from "./roleTaskPanelState";
import { chatSidebarHeaderClass, chatSidebarPanelClass, chatSidebarScrollableClass } from "./chatSidebarStyles";

/** Renders the compact role-task directory. */
export function RoleTaskList({ tasks, onCreate, onSelect }: {
  tasks: RoleTask[];
  onCreate: () => void;
  onSelect: (taskId: string) => void;
}) {
  const groups = groupRoleTasks(tasks);
  return (
    <div className={cx(chatSidebarPanelClass, "grid-rows-[auto_minmax(0,1fr)]")}>
      <div className={cx(chatSidebarHeaderClass, "gap-1")}>
        <span className="font-semibold text-ink">任务</span>
        <button
          className={cx("grid h-7 w-7 place-items-center rounded-md text-ink-muted transition-colors hover:bg-white hover:text-ink", focusResetClass)}
          type="button"
          aria-label="新增计划任务"
          onClick={onCreate}
        >
          <Plus className="h-4 w-4" weight="bold" />
        </button>
      </div>
      <div className={cx(chatSidebarScrollableClass, "space-y-3")}>
        {groups.length ? groups.map((group) => (
          <section key={group.kind} data-testid="role-task-group" className="rounded-md p-2">
            <div className="flex items-center gap-1.5 px-1 pb-2 text-[11px] font-medium tracking-wide text-ink-muted">
              {group.kind === "schedule" ? <CalendarDots className="h-3.5 w-3.5" weight="fill" /> : null}
              {group.kind === "subagent" ? <Robot className="h-3.5 w-3.5" weight="fill" /> : null}
              {group.kind === "memory_maintenance" ? <Brain className="h-3.5 w-3.5" weight="fill" /> : null}
              <span>{taskKindLabels[group.kind]}</span>
              <span className="ml-auto grid min-h-5 min-w-5 place-items-center rounded-md bg-surface-soft px-1 text-[10px] text-ink-muted">{group.tasks.length}</span>
            </div>
            {group.tasks.length ? group.tasks.map((task) => (
              <button
                key={`${task.kind}:${task.id}`}
                className={cx("group grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-2 rounded-md px-2.5 py-2.5 text-left transition-colors hover:bg-white focus-visible:bg-white", focusResetClass)}
                type="button"
                onClick={() => onSelect(task.id)}
              >
                <span className="min-w-0">
                  <span data-testid="role-task-title" className="block truncate text-[13px] font-semibold text-ink-secondary">{task.label}</span>
                  <span data-testid="role-task-summary" className="mt-1 block truncate text-[11px] text-ink-muted">{task.detail || "—"}</span>
                </span>
                <CaretRight className="h-3.5 w-3.5 text-ink-faint transition-colors group-hover:text-ink-muted" />
              </button>
            )) : null}
          </section>
        )) : null}
      </div>
    </div>
  );
}
