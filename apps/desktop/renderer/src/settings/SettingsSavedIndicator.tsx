import { Check } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { cx } from "@yinfengwindy/shiori-sdk";
import type { SettingsSavePhase } from "./settingsPageTypes";
import { isSettingsSaveCompleted, settingsSavedIndicatorMs } from "./settingsSaveState";

/**
 * A quiet "已保存" mark for autosaved settings. Each completed save restarts
 * one timer on the same element, so a run of edits keeps it steadily visible
 * instead of flashing once per save; failures stay with `SettingsSaveFeedback`.
 */
export function SettingsSavedIndicator({ phase, showPending = false }: {
  phase: SettingsSavePhase;
  /** Shows queued/in-flight work instead of an earlier saved confirmation. */
  showPending?: boolean;
}) {
  const [visible, setVisible] = useState(false);
  const previousPhaseRef = useRef(phase);

  useEffect(() => {
    const completed = isSettingsSaveCompleted(previousPhaseRef.current, phase);
    previousPhaseRef.current = phase;
    if (["error", "refresh-error", "unknown"].includes(phase)) setVisible(false);
    if (!completed) return undefined;
    setVisible(true);
    const timer = window.setTimeout(() => setVisible(false), settingsSavedIndicatorMs);
    return () => window.clearTimeout(timer);
  }, [phase]);

  const pending = showPending && phase === "saving";
  return (
    <div
      className={cx(
        "pointer-events-none inline-flex items-center gap-1 rounded-full bg-surface px-2.5 py-1 text-caption shadow-soft transition-opacity duration-[var(--duration-base)] ease-out-soft",
        pending ? "text-ink-muted" : "text-success-text",
        visible || pending ? "opacity-100" : "opacity-0",
      )}
      role="status"
      aria-hidden={!visible && !pending}
      data-testid="settings-saved-indicator"
    >
      {pending ? "正在保存…" : <><Check className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />已保存</>}
    </div>
  );
}
