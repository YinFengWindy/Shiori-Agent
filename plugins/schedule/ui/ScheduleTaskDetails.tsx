import { ArrowLeft, PencilSimple, Trash } from "@phosphor-icons/react";
import { useState } from "react";
import {
  chatSidebarHeaderClass,
  chatSidebarPanelClass,
  chatSidebarScrollableClass,
  compactGhostButtonClass,
  compactIconButtonClass,
  cx,
  DetailRow,
  type PluginHostServices,
} from "@yinfengwindy/shiori-sdk";
import { formatTimestamp } from "./format";
import { scheduleStatusLabels, scheduleTierLabels, scheduleTriggerLabels } from "./scheduleTaskFormState";
import type { ScheduledTask } from "./types";

/** Renders one scheduled task in full with its edit and cancel actions; it fills the task panel. */
export function ScheduleTaskDetails({ task, cancelling, error, host, onBack, onEdit, onCancel }: {
  task: ScheduledTask;
  cancelling: boolean;
  error: string;
  host: PluginHostServices;
  onBack: () => void;
  onEdit: () => void;
  onCancel: () => Promise<void>;
}) {
  const [confirming, setConfirming] = useState(false);
  const { InlineError, ConfirmDialog } = host.ui;
  const { schedule } = task;
  return (
    <div className={cx(chatSidebarPanelClass, "grid-rows-[auto_minmax(0,1fr)_auto]")}>
      <div className={cx(chatSidebarHeaderClass, "gap-2")}>
        <button className={compactIconButtonClass} type="button" aria-label="返回任务列表" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="min-w-0 truncate font-semibold text-ink">{task.label}</span>
      </div>
      <div className={cx(chatSidebarScrollableClass, "grid content-start gap-2")}>
        <DetailRow label="类型" value="计划任务" />
        <DetailRow label="状态" value={scheduleStatusLabels[task.status]} />
        <DetailRow label="执行模式" value={scheduleTierLabels[schedule.tier]} />
        <DetailRow label="触发方式" value={scheduleTriggerLabels[schedule.trigger]} />
        <DetailRow label="执行设置" value={schedule.when} />
        <DetailRow label="完整内容" value={task.detail} />
        <DetailRow label="创建时间" value={formatTimestamp(task.created_at)} />
        <DetailRow label="下次运行" value={formatTimestamp(task.next_run_at)} />
      </div>
      <div className="grid gap-2 pt-3">
        {!task.editable ? <div className="text-xs text-warning-text">任务运行期间不可编辑</div> : null}
        {error && !confirming ? <InlineError message={error} /> : null}
        <div className="flex justify-end gap-2">
          <button className={compactGhostButtonClass} type="button" disabled={!task.editable} onClick={onEdit}>
            <PencilSimple className="h-4 w-4" />编辑
          </button>
          <button className={compactGhostButtonClass} type="button" onClick={() => setConfirming(true)}>
            <Trash className="h-4 w-4" />取消
          </button>
        </div>
      </div>
      <ConfirmDialog
        open={confirming}
        title="取消计划任务"
        description={`「${task.label}」将不再执行。`}
        confirmLabel="确认取消"
        busyLabel="取消中…"
        cancelLabel="返回"
        destructive
        busy={cancelling}
        error={confirming ? error : undefined}
        onClose={() => setConfirming(false)}
        onConfirm={() => {
          // A failure stays in the dialog through `error`.
          void onCancel().catch(() => undefined);
        }}
      />
    </div>
  );
}
