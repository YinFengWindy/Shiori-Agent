import { useState } from "react";
import { ArrowSquareOut, ArrowBendUpRight, Stop, GitBranch, Clock, TerminalWindow } from "@phosphor-icons/react";
import { compactGhostButtonClass, cx, textareaClass, type PluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { canCancel, canContinue, formatTime, stageLabels, taskTitle } from "./selectors";
import { TaskBadge } from "./TaskList";
import { TaskOutput } from "./TaskOutput";
import { useTaskActions } from "./useTaskActions";
import type { HerdrTask, TaskStage } from "./types";

const stages: TaskStage[] = ["preparing", "analysis", "implementation", "validation", "pull_request"];

/** Detail sections keep their DOM identity across progress updates and stage regressions. */
export function TaskDetail({ task, roleName, client, host, connected, refresh }: { task: HerdrTask; roleName: string; client: PluginRpcClient; host: PluginHostServices; connected: boolean; refresh: () => Promise<void> }) {
  const [dialog, setDialog] = useState<"continue" | "cancel" | null>(null);
  const [requirement, setRequirement] = useState("");
  const actions = useTaskActions(task, client, host, refresh);
  const busy = Boolean(actions.pending);
  const events = task.progress_events.filter((event) => event.run_id === task.run_id);
  const confirm = async () => { if (dialog && await actions.run(dialog, requirement)) { setDialog(null); setRequirement(""); } };
  return <article className="herdr-task-detail min-h-0 min-w-0 overflow-y-auto p-6" aria-label="任务详情">
    <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-2"><TaskBadge task={task} /><span className="text-body-sm text-ink-muted">{roleName} · {task.agent === "codex" ? "Codex" : "Claude Code"}</span></div><span className="text-caption text-ink-muted">同步于 {formatTime(task.updated_at)}</span></div>
    <h2 className="mt-4 break-words font-display text-title">{taskTitle(task)}</h2>
    <div className="mt-3 grid gap-1 text-caption text-ink-muted"><span className="flex min-w-0 items-center gap-1.5"><GitBranch className="h-4 w-4 shrink-0" aria-hidden="true" /><span className="break-all">{task.branch}</span></span><span className="break-all">{task.worktree || task.repository}</span></div>
    <div className="mt-5 flex flex-wrap gap-2">
      <button type="button" className={compactGhostButtonClass} disabled={!connected || busy || !canContinue(task)} onClick={() => { actions.clearError(); setDialog("continue"); }}><ArrowBendUpRight className="h-4 w-4" aria-hidden="true" />继续任务</button>
      <button type="button" className={compactGhostButtonClass} disabled={!connected || busy || !canCancel(task)} onClick={() => { actions.clearError(); setDialog("cancel"); }}><Stop className="h-4 w-4" aria-hidden="true" />{task.status === "cancelling" ? "取消中…" : "取消任务"}</button>
      {task.pr_url ? <button type="button" className={compactGhostButtonClass} disabled={busy} onClick={() => { void actions.run("open_pr"); }}><ArrowSquareOut className="h-4 w-4" aria-hidden="true" />打开 Draft PR</button> : null}
    </div>
    {!dialog && actions.error ? <host.ui.InlineError message={actions.error} className="mt-4" /> : null}
    {task.error ? <host.ui.InlineError title="任务需要处理" message={task.error} className="mt-5" persona={false} /> : null}
    {task.report_error ? <host.ui.InlineError title="聊天回报失败" message={task.report_error} className="mt-4" persona={false} /> : null}
    <section className="mt-7" aria-label="当前阶段"><div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="text-body font-medium">当前阶段</h3><span className="text-caption text-ink-muted">最后报告 · {formatTime(task.progress_updated_at)}</span></div>
      <ol className="mt-3 flex flex-wrap gap-2">{stages.map((stage) => <li key={stage} aria-current={task.stage === stage ? "step" : undefined} className={cx("rounded-md border px-3 py-2 text-body-sm", task.stage === stage ? "border-line-accent bg-accent-softer font-medium text-accent-text" : "border-line-soft text-ink-muted")}>{stageLabels[stage]}</li>)}</ol>
      {!task.stage ? <p className="mt-3 text-body-sm text-ink-muted">尚无阶段报告</p> : null}
      {task.progress_notice ? <p role="status" className="mt-3 text-body-sm text-warning-text">{task.progress_notice}</p> : null}
    </section>
    <section className="mt-7" aria-label="活动记录"><h3 className="mb-3 flex items-center gap-2 text-body font-medium"><Clock className="h-4 w-4 text-ink-muted" aria-hidden="true" />活动记录</h3>
      {events.length ? <ol className="herdr-timeline grid gap-4">{events.map((event, index) => <li key={`${event.source}:${event.sequence}:${index}`} className="border-l border-line pl-4"><div className="flex flex-wrap items-baseline justify-between gap-2"><span className="text-body-sm font-medium">{stageLabels[event.stage]}</span><time className="text-caption text-ink-muted">{formatTime(event.observed_at)}</time></div>{event.detail ? <p className="mt-1 break-words text-body-sm text-ink-secondary">{event.detail}</p> : null}</li>)}</ol> : <p className="text-body-sm text-ink-muted">暂无活动记录</p>}
    </section>
    <div className="mt-7"><TaskOutput key={`${task.id}:${task.run_id}`} output={task.output} /></div>
    {task.summary ? <section className="mt-7"><h3 className="mb-3 text-body font-medium">修改摘要</h3><p className="whitespace-pre-wrap break-words text-body-sm text-ink-secondary">{task.summary}</p></section> : null}
    {task.validation.length ? <section className="mt-7" aria-label="验证结果"><h3 className="mb-3 flex items-center gap-2 text-body font-medium"><TerminalWindow className="h-4 w-4 text-ink-muted" aria-hidden="true" />验证结果</h3><div className="grid gap-2">{task.validation.map((check, index) => <details key={index} className="rounded-md border border-line-soft p-3"><summary className="cursor-pointer break-all text-body-sm"><span className={check.exit_code === 0 ? "text-success-text" : "text-warning-text"}>{check.exit_code === 0 ? "通过" : "未通过"}</span> · {check.argv.join(" ")}</summary><pre className="mt-3 max-h-48 overflow-auto whitespace-pre-wrap break-all text-caption text-ink-secondary">{check.output}</pre></details>)}</div></section> : null}
    <details className="mt-7 border-t border-line-soft pt-4"><summary className="cursor-pointer text-body-sm text-ink-muted">完整任务要求</summary><p className="mt-3 whitespace-pre-wrap break-words text-body-sm text-ink-secondary">{task.requirement}</p></details>
    <host.ui.ConfirmDialog open={dialog !== null} title={dialog === "continue" ? "继续任务" : "取消当前任务？"} description={dialog === "continue" ? "追加要求" : "保留工作区和已有修改。"} confirmLabel={dialog === "continue" ? "提交追加要求" : "确认取消"} destructive={dialog === "cancel"} persona={false} busy={busy} busyLabel={dialog === "continue" ? "提交中…" : "取消中…"} error={actions.error} confirmDisabled={!connected || (dialog === "continue" && !requirement.trim())} onClose={() => { if (!busy) setDialog(null); }} onConfirm={() => { void confirm(); }}>
      {dialog === "continue" ? <textarea aria-label="追加要求" value={requirement} onChange={(event) => setRequirement(event.target.value)} className={textareaClass} autoFocus /> : null}
    </host.ui.ConfirmDialog>
  </article>;
}
