import type { TaskStage, TaskStatus, TaskSummary } from "./types";

/** Chinese labels of the service's task states. */
export const statusLabels: Record<TaskStatus, string> = {
  queued: "等待开始",
  preparing: "准备中",
  running: "执行中",
  completed: "已交付",
  blocked: "等待处理",
  unknown: "状态待确认",
  failed: "失败",
  cancelling: "取消中",
  cancelled: "已取消",
  monitoring_stopped: "已停止追踪",
};

/** Stage order of the stage track; reports may still move backwards. */
export const stageOrder: readonly TaskStage[] = ["preparing", "analysis", "implementation", "validation", "pull_request"];

/** Chinese labels of reported stages. */
export const stageLabels: Record<TaskStage, string> = {
  preparing: "准备",
  analysis: "分析",
  implementation: "实现",
  validation: "验证",
  pull_request: "创建 PR",
};

/** Semantic color family of a status, for the status dot and badge. */
export type StatusTone = "accent" | "success" | "warning" | "danger" | "muted";

const statusTones: Record<TaskStatus, StatusTone> = {
  queued: "accent",
  preparing: "accent",
  running: "accent",
  cancelling: "accent",
  completed: "success",
  blocked: "warning",
  unknown: "warning",
  failed: "danger",
  cancelled: "muted",
  monitoring_stopped: "muted",
};

/** Tone of a status. */
export function statusTone(status: TaskStatus): StatusTone {
  return statusTones[status];
}

/** Statuses whose run is still under way. */
const activeStatuses: ReadonlySet<TaskStatus> = new Set(["queued", "preparing", "running", "cancelling"]);

/** Statuses that need nothing more; blocked and unknown tasks still wait for the user. */
const finishedStatuses: ReadonlySet<TaskStatus> = new Set(["completed", "cancelled", "failed", "monitoring_stopped"]);

/** Splits the newest-first list into 进行中 / 已结束, keeping order inside each group. */
export function groupTasks(tasks: readonly TaskSummary[]) {
  return {
    active: tasks.filter((task) => !finishedStatuses.has(task.status)),
    finished: tasks.filter((task) => finishedStatuses.has(task.status)),
  };
}

/** The status, or the current stage while a run is under way. */
export function phaseLabel(task: Pick<TaskSummary, "status" | "stage">) {
  return activeStatuses.has(task.status) && task.stage ? stageLabels[task.stage] : statusLabels[task.status];
}

/** Display name of the coding agent. */
export function agentLabel(agent: TaskSummary["agent"]) {
  return agent === "codex" ? "Codex" : "Claude Code";
}

/** Last path segment of a repository path. */
export function repositoryName(path: string) {
  return path.replaceAll("\\", "/").split("/").filter(Boolean).at(-1) ?? path;
}

/** Task title; the service derives it from the first requirement line. */
export function taskTitle(task: Pick<TaskSummary, "title">) {
  return task.title || "未命名任务";
}

/** Coarse relative time for list rows: 刚刚 / N 分钟前 / N 小时前 / N 天前, then the date. */
export function relativeTime(timestamp: string, now: Date) {
  const time = new Date(timestamp).getTime();
  if (!timestamp || Number.isNaN(time)) return "";
  const minutes = Math.floor((now.getTime() - time) / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  if (minutes < 24 * 60) return `${Math.floor(minutes / 60)} 小时前`;
  if (minutes < 7 * 24 * 60) return `${Math.floor(minutes / (24 * 60))} 天前`;
  return new Date(time).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

/** Clock time of a progress report. */
export function clockTime(timestamp: string) {
  const time = new Date(timestamp);
  if (!timestamp || Number.isNaN(time.getTime())) return "";
  return time.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}
