import { ArrowLeft, PencilSimple, Trash } from "@phosphor-icons/react";
import { formatTimestamp } from "../shared/format";
import type { RoleTask } from "../shared/types";
import {
  scheduleTierLabels,
  scheduleTriggerLabels,
  taskKindLabels,
  taskStatusLabels,
} from "./roleTaskPanelState";

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 border-b border-[#E6EBF2] py-3 last:border-b-0">
      <span className="text-[11px] text-[#98A2B3]">{label}</span>
      <span className="break-words text-xs text-[#334155]">{value || "—"}</span>
    </div>
  );
}

/** Renders complete task information and its supported actions. */
export function RoleTaskDetails({ task, cancelling, error, confirmingCancel, onBack, onEdit, onBeginCancel, onCancel, onDismissCancel }: {
  task: RoleTask;
  cancelling: boolean;
  error: string;
  confirmingCancel: boolean;
  onBack: () => void;
  onEdit: () => void;
  onBeginCancel: () => void;
  onCancel: () => void;
  onDismissCancel: () => void;
}) {
  const schedule = task.schedule;
  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)_auto] rounded-[20px] bg-[#F1F5F9] p-4 text-sm text-[#334155]">
      <div className="flex items-center gap-2 pb-3">
        <button className="grid h-8 w-8 place-items-center rounded-md transition hover:bg-white" type="button" aria-label="返回任务列表" onClick={onBack}>
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="min-w-0 truncate font-semibold text-[#272536]">{task.label}</span>
      </div>
      <div className="min-h-0 overflow-y-auto rounded-[16px] bg-white/90 px-4">
        <DetailRow label="类型" value={taskKindLabels[task.kind]} />
        <DetailRow label="状态" value={taskStatusLabels[task.status] ?? task.status} />
        {schedule ? <DetailRow label="执行模式" value={scheduleTierLabels[schedule.tier]} /> : null}
        {schedule ? <DetailRow label="触发方式" value={scheduleTriggerLabels[schedule.trigger]} /> : null}
        {schedule ? <DetailRow label="执行设置" value={schedule.when} /> : null}
        <DetailRow label="完整内容" value={task.detail} />
        <DetailRow label="创建时间" value={formatTimestamp(task.created_at)} />
        {task.next_run_at ? <DetailRow label="下次运行" value={formatTimestamp(task.next_run_at)} /> : null}
      </div>
      <div className="grid gap-2 pt-3">
        {task.kind === "schedule" && !task.editable ? <div className="text-xs text-[#B45309]">任务运行期间不可编辑</div> : null}
        {error ? <div className="text-xs text-[#B42318]">{error}</div> : null}
        {confirmingCancel ? (
          <div className="flex items-center justify-end gap-2">
            <span className="mr-auto text-xs text-[#667085]">确认取消此任务？</span>
            <button className="rounded-md px-3 py-2 text-xs transition hover:bg-white" type="button" disabled={cancelling} onClick={onDismissCancel}>返回</button>
            <button className="rounded-md bg-[#B42318] px-3 py-2 text-xs text-white transition hover:bg-[#912018] disabled:opacity-50" type="button" disabled={cancelling} onClick={onCancel}>{cancelling ? "取消中…" : "确认取消"}</button>
          </div>
        ) : (
          <div className="flex justify-end gap-2">
            {task.kind === "schedule" ? (
              <button className="inline-flex items-center gap-1 rounded-md border border-[#D8DFE7] px-3 py-2 text-xs transition hover:border-[#B8C2CE] disabled:opacity-50" type="button" disabled={!task.editable} onClick={onEdit}>
                <PencilSimple className="h-4 w-4" />编辑
              </button>
            ) : null}
            {task.cancellable ? (
              <button className="inline-flex items-center gap-1 rounded-md border border-[#E6B8B3] px-3 py-2 text-xs text-[#B42318] transition hover:border-[#B42318]" type="button" onClick={onBeginCancel}>
                <Trash className="h-4 w-4" />取消
              </button>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
