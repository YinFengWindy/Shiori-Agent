import type { RoleTask, RoleTaskKind } from "../shared/types";

export type RoleTaskPanelView =
  | { kind: "list" }
  | { kind: "detail"; taskId: string }
  | { kind: "create" }
  | { kind: "edit"; taskId: string };

export type RoleTaskPanelAction =
  | { type: "show-list" }
  | { type: "show-create" }
  | { type: "show-detail"; taskId: string }
  | { type: "show-edit"; taskId: string };

export const taskKindLabels: Record<RoleTaskKind, string> = {
  schedule: "计划任务",
  subagent: "后台任务",
  memory_maintenance: "记忆维护",
};

export const taskStatusLabels: Record<string, string> = {
  running: "进行中",
  scheduled: "待执行",
};

export const scheduleTierLabels = {
  instant: "直接发送",
  soft: "AI 生成",
} as const;

export const scheduleTriggerLabels = {
  at: "指定时间",
  after: "延迟执行",
  every: "循环执行",
} as const;

/** Groups role tasks in the stable order used by the task sidebar. */
export function groupRoleTasks(tasks: RoleTask[]): Array<{ kind: RoleTaskKind; tasks: RoleTask[] }> {
  return (["schedule", "subagent", "memory_maintenance"] as const)
    .map((kind) => ({ kind, tasks: tasks.filter((task) => task.kind === kind) }))
    .filter((group) => group.tasks.length > 0);
}

/** Applies one explicit navigation action within the task panel. */
export function reduceRoleTaskPanelView(_view: RoleTaskPanelView, action: RoleTaskPanelAction): RoleTaskPanelView {
  switch (action.type) {
    case "show-list": return { kind: "list" };
    case "show-create": return { kind: "create" };
    case "show-detail": return { kind: "detail", taskId: action.taskId };
    case "show-edit": return { kind: "edit", taskId: action.taskId };
  }
}

/** Returns a safe panel view after the task snapshot changes. */
export function reconcileRoleTaskPanelView(view: RoleTaskPanelView, tasks: RoleTask[]): RoleTaskPanelView {
  if (view.kind !== "detail" && view.kind !== "edit") return view;
  const task = tasks.find((item) => item.id === view.taskId);
  if (!task) return { kind: "list" };
  if (view.kind === "edit" && !task.editable) return { kind: "detail", taskId: task.id };
  return view;
}
