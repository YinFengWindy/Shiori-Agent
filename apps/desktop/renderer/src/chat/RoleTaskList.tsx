import type { ReactNode } from "react";
import { Brain, CaretRight, Robot } from "@phosphor-icons/react";
import type { RoleTask } from "../shared/types";
import {
  cx,
  roleTaskGroupCountClass,
  roleTaskGroupHeadClass,
  roleTaskRowClass,
  roleTaskRowSummaryClass,
  roleTaskRowTitleClass,
} from "@yinfengwindy/shiori-sdk";
import { groupRoleTasks, taskKindLabels } from "./roleTaskPanelState";
import { chatSidebarHeaderClass, chatSidebarPanelClass, chatSidebarScrollableClass } from "./chatSidebarStyles";

/** Renders the compact role-task directory; `block` is the plugin's group, shown first. */
export function RoleTaskList({ tasks, block, onSelect }: {
  tasks: RoleTask[];
  block: ReactNode;
  onSelect: (taskId: string) => void;
}) {
  const groups = groupRoleTasks(tasks);
  return (
    <div className={cx(chatSidebarPanelClass, "grid-rows-[auto_minmax(0,1fr)]")}>
      <div className={cx(chatSidebarHeaderClass, "gap-1")}>
        <span className="font-semibold text-ink">任务</span>
      </div>
      <div className={cx(chatSidebarScrollableClass, "space-y-3")}>
        {block}
        {groups.map((group) => (
          <section key={group.kind} data-testid="role-task-group" className="rounded-md p-2">
            <div className={roleTaskGroupHeadClass}>
              {group.kind === "subagent" ? <Robot className="h-3.5 w-3.5" weight="fill" /> : null}
              {group.kind === "memory_maintenance" ? <Brain className="h-3.5 w-3.5" weight="fill" /> : null}
              <span>{taskKindLabels[group.kind]}</span>
              <span className={roleTaskGroupCountClass}>{group.tasks.length}</span>
            </div>
            {group.tasks.map((task) => (
              <button
                key={`${task.kind}:${task.id}`}
                className={roleTaskRowClass}
                type="button"
                onClick={() => onSelect(task.id)}
              >
                <span className="min-w-0">
                  <span data-testid="role-task-title" className={roleTaskRowTitleClass}>{task.label}</span>
                  <span data-testid="role-task-summary" className={roleTaskRowSummaryClass}>{task.detail || "—"}</span>
                </span>
                <CaretRight className="h-3.5 w-3.5 text-ink-faint transition-colors group-hover:text-ink-muted" />
              </button>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}
