import { GitBranch, Robot, CaretRight } from "@phosphor-icons/react";
import { badgeClass, cx, sidebarNavItemClass } from "@yinfengwindy/shiori-sdk";
import { formatTime, repositoryName, stageLabels, statusLabels, taskTitle } from "./selectors";
import type { HerdrTask } from "./types";

/** A status has a static label even when an agent is working. */
export function TaskBadge({ task }: { task: HerdrTask }) {
  const tone = task.status === "completed" ? "success" : ["blocked", "unknown", "failed"].includes(task.status) ? "warning" : ["cancelled", "monitoring_stopped"].includes(task.status) ? "muted" : "accent";
  return <span className={cx(badgeClass, "herdr-status shrink-0")} data-tone={tone}>{statusLabels[task.status]}</span>;
}

/** Keyboard-accessible master list; updates never replace the scroll container. */
export function TaskList({ tasks, selectedId, names, onSelect }: { tasks: readonly HerdrTask[]; selectedId: string; names: ReadonlyMap<string, string>; onSelect: (id: string) => void }) {
  return <div className="herdr-task-list min-h-0 overflow-y-auto p-2" aria-label="任务列表">
    {tasks.length ? tasks.map((task) => <button key={task.id} type="button" onClick={() => onSelect(task.id)} aria-pressed={task.id === selectedId}
      className={cx(sidebarNavItemClass, "herdr-task-row mb-1 flex w-full flex-col gap-3 p-4 text-left", task.id === selectedId && "bg-surface-active")}>
      <div className="flex w-full items-start justify-between gap-3"><span className="line-clamp-2 text-body font-medium text-ink">{taskTitle(task)}</span><CaretRight className="mt-1 h-4 w-4 shrink-0 text-ink-muted" aria-hidden="true" /></div>
      <div className="flex w-full items-center justify-between gap-2"><TaskBadge task={task} /><span className="text-body-sm text-ink-muted">{task.stage ? stageLabels[task.stage] : "尚无阶段报告"}</span></div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption text-ink-muted"><span>{names.get(task.role_id) ?? task.role_id}</span><span className="inline-flex items-center gap-1"><Robot className="h-3.5 w-3.5" aria-hidden="true" />{task.agent === "codex" ? "Codex" : "Claude Code"}</span></div>
      <div className="flex min-w-0 items-center gap-1.5 text-caption text-ink-muted"><GitBranch className="h-3.5 w-3.5 shrink-0" aria-hidden="true" /><span className="truncate" title={task.repository}>{repositoryName(task.repository)}</span></div>
      <span className="text-caption text-ink-muted">阶段报告 · {formatTime(task.progress_updated_at)}</span>
    </button>) : <div className="px-5 py-12 text-center text-body text-ink-muted">没有符合筛选条件的任务</div>}
  </div>;
}
