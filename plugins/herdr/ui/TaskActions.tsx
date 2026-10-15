import { useState } from "react";
import { ArrowSquareOut, Stop } from "@phosphor-icons/react";
import { compactGhostButtonClass, errorMessage, type PluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { TaskDetail, TaskDetailResponse } from "./types";

/** Asks for confirmation; the task shows 已取消 only once the service confirms the stop. */
export function CancelTaskButton({ task, connected, client, host, onApplied }: {
  task: TaskDetail;
  connected: boolean;
  client: PluginRpcClient;
  host: PluginHostServices;
  onApplied: (response: TaskDetailResponse) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const confirm = async () => {
    setPending(true);
    setError("");
    try {
      onApplied(await client.call<TaskDetailResponse>("tasks.cancel", { task_id: task.id }));
      setOpen(false);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setPending(false);
    }
  };
  // Delivered, cancelled or already cancelling: there is nothing to cancel.
  if (!task.can_cancel) return null;
  return (
    <>
      <button type="button" className={compactGhostButtonClass} disabled={!connected} onClick={() => { setError(""); setOpen(true); }}>
        <Stop className="h-4 w-4" aria-hidden="true" />
        取消
      </button>
      <host.ui.ConfirmDialog
        open={open}
        title="取消任务？"
        description="保留工作区和已有修改。"
        confirmLabel="确认取消"
        cancelLabel="返回"
        destructive
        busy={pending}
        busyLabel="取消中…"
        error={error}
        confirmDisabled={!connected}
        onClose={() => { if (!pending) setOpen(false); }}
        onConfirm={() => { void confirm(); }}
      />
    </>
  );
}

/** Opens the verified Draft PR in the browser through the host. */
export function OpenPullRequestButton({ url, host, className = compactGhostButtonClass }: { url: string; host: PluginHostServices; className?: string }) {
  const open = () => {
    host.openExternal(url).catch((error: unknown) => {
      host.feedback.error("打开 Draft PR 失败", { detail: errorMessage(error) });
    });
  };
  return (
    <button type="button" className={className} onClick={open}>
      <ArrowSquareOut className="h-4 w-4" aria-hidden="true" />
      打开 Draft PR
    </button>
  );
}
