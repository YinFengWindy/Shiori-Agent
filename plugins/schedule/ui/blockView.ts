import type { ScheduledTask } from "./types";

/** The block's own views; the host keeps them as the `view` token of the `roleTasks` slot. */
export type ScheduleBlockView =
  | { kind: "list" }
  | { kind: "create" }
  | { kind: "detail"; taskId: string }
  | { kind: "edit"; taskId: string };

/** The token the host keeps for `view`; the list is `""`, the block's group inside the task list. */
export function formatBlockView(view: ScheduleBlockView): string {
  switch (view.kind) {
    case "list": return "";
    case "create": return "create";
    case "detail": return `detail:${view.taskId}`;
    case "edit": return `edit:${view.taskId}`;
  }
}

/** Reads the host's `view` token; anything unknown is the list. */
export function parseBlockView(token: string): ScheduleBlockView {
  if (token === "create") return { kind: "create" };
  const separator = token.indexOf(":");
  const taskId = separator > 0 ? token.slice(separator + 1) : "";
  if (!taskId) return { kind: "list" };
  const kind = token.slice(0, separator);
  if (kind === "detail") return { kind: "detail", taskId };
  if (kind === "edit") return { kind: "edit", taskId };
  return { kind: "list" };
}

/**
 * A view that is still valid for the role's jobs. Before the first read
 * (`tasks` is `null`) every view stands; then a removed job returns to the
 * list and a running one cannot be edited.
 */
export function reconcileBlockView(view: ScheduleBlockView, tasks: ScheduledTask[] | null): ScheduleBlockView {
  if (tasks === null || (view.kind !== "detail" && view.kind !== "edit")) return view;
  const task = tasks.find((item) => item.id === view.taskId);
  if (!task) return { kind: "list" };
  if (view.kind === "edit" && !task.editable) return { kind: "detail", taskId: task.id };
  return view;
}
