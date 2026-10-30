import { ArrowLeft, Trash } from "@phosphor-icons/react";
import { InlineError } from "../shared/feedback/InlineError";
import { formatTimestamp } from "../shared/format";
import type { RoleTask } from "../shared/types";
import { cx, DetailRow } from "@yinfengwindy/shiori-sdk";
import { focusResetClass } from "../shared/styles";
import { taskKindLabels, taskStatusLabels } from "./roleTaskPanelState";
import {
  chatSidebarBackButtonClass,
  chatSidebarHeaderClass,
  chatSidebarPanelClass,
  chatSidebarScrollableClass,
} from "./chatSidebarStyles";

/** Renders one host task's information and, when it can be cancelled, its cancel action. */
export function RoleTaskDetails({ task, cancelling, error, confirmingCancel, onBack, onBeginCancel, onCancel, onDismissCancel }: {
  task: RoleTask;
  cancelling: boolean;
  error: string;
  confirmingCancel: boolean;
  onBack: () => void;
  onBeginCancel: () => void;
  onCancel: () => void;
  onDismissCancel: () => void;
}) {
  return (
    <div className={cx(chatSidebarPanelClass, "grid-rows-[auto_minmax(0,1fr)_auto]")}>
      <div className={cx(chatSidebarHeaderClass, "gap-2")}>
        <button className={chatSidebarBackButtonClass} type="button" aria-label="返回任务列表" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="min-w-0 truncate font-semibold text-ink">{task.label}</span>
      </div>
      <div className={cx(chatSidebarScrollableClass, "grid content-start gap-2")}>
        <DetailRow label="类型" value={taskKindLabels[task.kind]} />
        <DetailRow label="状态" value={taskStatusLabels[task.status] ?? task.status} />
        <DetailRow label="完整内容" value={task.detail} />
        <DetailRow label="创建时间" value={formatTimestamp(task.created_at)} />
      </div>
      <div className="grid gap-2 pt-3">
        {error ? <InlineError message={error} /> : null}
        {confirmingCancel ? (
          <div className="flex items-center justify-end gap-2 rounded-md p-2">
            <span className="mr-auto text-xs text-ink-muted">确认取消此任务？</span>
            <button className={cx("rounded-md px-3 py-2 text-xs transition-colors hover:bg-surface-soft", focusResetClass)} type="button" disabled={cancelling} onClick={onDismissCancel}>返回</button>
            <button className={cx("rounded-md bg-danger px-3 py-2 text-xs text-white transition hover:bg-[var(--danger-700)] disabled:opacity-50", focusResetClass)} type="button" disabled={cancelling} onClick={onCancel}>{cancelling ? "取消中…" : "确认取消"}</button>
          </div>
        ) : task.cancellable ? (
          <div className="flex justify-end gap-2">
            <button className={cx("inline-flex items-center gap-1 rounded-md border border-[var(--danger-300)] bg-white/70 px-3 py-2 text-xs text-danger-text transition-colors hover:border-danger hover:bg-white", focusResetClass)} type="button" onClick={onBeginCancel}>
              <Trash className="h-4 w-4" />取消
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
