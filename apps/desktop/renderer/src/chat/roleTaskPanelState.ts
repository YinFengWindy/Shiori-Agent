import type { RoleTask, RoleTaskKind } from "../shared/types";

/**
 * Which view fills the task panel: the task list, a host task's details, or
 * a view of the plugin block (`blockView`, a token the block defines).
 */
export type RoleTaskPanelView =
  | { kind: "list" }
  | { kind: "detail"; taskId: string }
  | { kind: "block"; blockView: string };

export const taskKindLabels: Record<RoleTaskKind, string> = {
  subagent: "后台任务",
  memory_maintenance: "记忆维护",
};

export const taskStatusLabels: Record<string, string> = {
  running: "进行中",
};

/** Groups the host's role tasks in the stable order used by the task sidebar. */
export function groupRoleTasks(tasks: RoleTask[]): Array<{ kind: RoleTaskKind; tasks: RoleTask[] }> {
  return (["subagent", "memory_maintenance"] as const)
    .map((kind) => ({ kind, tasks: tasks.filter((task) => task.kind === kind) }));
}

/** The panel view after the plugin block asks for one of its views; `""` returns to the list. */
export function blockPanelView(blockView: string): RoleTaskPanelView {
  return blockView ? { kind: "block", blockView } : { kind: "list" };
}

/** Returns a safe panel view after the host's task snapshot changes. */
export function reconcileRoleTaskPanelView(view: RoleTaskPanelView, tasks: RoleTask[]): RoleTaskPanelView {
  if (view.kind !== "detail") return view;
  return tasks.some((item) => item.id === view.taskId) ? view : { kind: "list" };
}
