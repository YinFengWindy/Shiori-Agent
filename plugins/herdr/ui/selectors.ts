import type { HerdrTask, TaskStage, TaskStatus } from "./types";

/** Chinese labels for authoritative task states. */
export const statusLabels: Record<TaskStatus, string> = { queued: "等待开始", preparing: "准备中", running: "执行中", completed: "已交付", blocked: "等待处理", unknown: "状态待确认", failed: "失败", cancelling: "取消中", cancelled: "已取消", monitoring_stopped: "已停止追踪" };
/** Stage order is presentation only; reported progress may return to an earlier stage. */
export const stageLabels: Record<TaskStage, string> = { preparing: "准备", analysis: "分析", implementation: "实现", validation: "验证", pull_request: "创建 PR" };
/** Filters are independent of the host's ambient chat role. */
export type TaskFilters = { role: string; repository: string; status: string };
/** Match exact filter identities without copying task state into another model. */
export function filterTasks(tasks: readonly HerdrTask[], filters: TaskFilters) {
  return tasks.filter((task) => (!filters.role || task.role_id === filters.role) && (!filters.repository || task.repository === filters.repository) && (!filters.status || task.status === filters.status));
}
/** Use a compact repository label while preserving its absolute path in the UI. */
export function repositoryName(path: string) { return path.replaceAll("\\", "/").split("/").filter(Boolean).at(-1) ?? path; }
/** The first nonempty requirement line names the task without an invented title. */
export function taskTitle(task: HerdrTask) { return task.requirement.split(/\r?\n/).find((line) => line.trim())?.trim() ?? "未命名任务"; }
/** Explicit task controls, not optimistic state transitions. */
export function canContinue(task: HerdrTask) { return task.can_continue && Boolean(task.worktree) && !["queued", "preparing", "running", "cancelling", "monitoring_stopped"].includes(task.status); }
/** Completed delivery cannot be overwritten by a late cancellation. */
export function canCancel(task: HerdrTask) { return !["completed", "cancelled", "cancelling", "monitoring_stopped"].includes(task.status); }
/** Use report timestamps for activity, never the observer's synchronization heartbeat. */
export function formatTime(timestamp: string) { return timestamp ? new Date(timestamp).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }) : "尚无报告"; }
