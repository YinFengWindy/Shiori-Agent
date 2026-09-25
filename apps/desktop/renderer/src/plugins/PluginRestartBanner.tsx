import { ArrowsClockwise } from "@phosphor-icons/react";
import { useState } from "react";
import { hasInFlightChatTurns } from "../shared/chatTurnActivity";
import { errorMessage } from "../shared/feedback/feedbackStore";
import { mascotFeedback as feedback } from "../shared/mascot/mascotFeedback";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";
import { cx } from "../shared/styles";
import type { PluginSummary } from "./pluginBridgeClient";

/**
 * Plugins whose queued change only lands on the next launch: a staged
 * install / update / uninstall, a trust grant, or a plugin the host could
 * not swap in place (`RESTART_REQUIRED`).
 */
export function pluginsAwaitingRestart(plugins: readonly PluginSummary[]): PluginSummary[] {
  return plugins.filter((plugin) => Boolean(plugin.pendingOperation) || Boolean(plugin.trustPendingRestart) || plugin.state === "RESTART_REQUIRED");
}

/** Pairs the per-row "待重启" labels with the one action that applies them: relaunching Shiori. */
export function PluginRestartBanner({ plugins }: { plugins: readonly PluginSummary[] }) {
  const [relaunching, setRelaunching] = useState(false);
  // Relaunching kills a reply mid-stream, so that case is confirmed first.
  const [confirmingInterrupt, setConfirmingInterrupt] = useState(false);
  const count = pluginsAwaitingRestart(plugins).length;
  if (count === 0) return null;

  function requestRelaunch() {
    if (hasInFlightChatTurns()) {
      setConfirmingInterrupt(true);
      return;
    }
    void relaunch();
  }

  async function relaunch() {
    setConfirmingInterrupt(false);
    setRelaunching(true);
    try {
      if (!await window.miraDesktop.relaunchApp()) {
        feedback.error("无法从当前窗口重启 Shiori");
        setRelaunching(false);
      }
    } catch (error) {
      feedback.error(`重启失败：${errorMessage(error)}`);
      setRelaunching(false);
    }
  }

  return (
    <div className="mb-4 flex items-center gap-3 rounded-lg bg-lavender-soft px-4 py-2.5 text-body text-lavender-text" role="status" data-testid="plugin-restart-banner">
      <ArrowsClockwise className="h-4 w-4 shrink-0" weight="bold" aria-hidden="true" />
      <span className="min-w-0 flex-1">有 {count} 项更改需要重启后生效</span>
      <button
        type="button"
        className={cx(
          "shrink-0 rounded-md border border-line bg-surface px-3 py-1 text-body-sm font-medium text-lavender-text transition-colors hover:bg-surface-hover",
          "disabled:cursor-default disabled:opacity-60",
        )}
        disabled={relaunching}
        onClick={requestRelaunch}
      >
        {relaunching ? "正在重启…" : "立即重启"}
      </button>
      <ConfirmDialog
        open={confirmingInterrupt}
        title="重启 Shiori？"
        description="有对话正在进行，重启会中断它。"
        confirmLabel="继续重启"
        onClose={() => setConfirmingInterrupt(false)}
        onConfirm={() => void relaunch()}
      />
    </div>
  );
}
