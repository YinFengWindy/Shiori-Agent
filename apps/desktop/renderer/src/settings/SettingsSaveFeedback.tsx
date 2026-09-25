import type { SettingsSavePhase } from "./settingsPageTypes";
import { shouldShowSettingsFeedback } from "./settingsSaveState";
import { InlineError } from "../shared/feedback/InlineError";
import { ArrowClockwise, ArrowsClockwise } from "@phosphor-icons/react";

const iconButtonClass = "shrink-0 rounded-md p-1 text-danger-text hover:bg-white/70";

/** Renders terminal settings save feedback above the page content (吟风 fronts it when the 看板娘 is on). */
export function SettingsSaveFeedback({
  phase,
  message,
  onRetry,
  onReload,
}: {
  phase: SettingsSavePhase;
  message: string;
  onRetry?: () => void;
  onReload?: () => void;
}) {
  if (!shouldShowSettingsFeedback(phase, message)) return null;
  const actions = onRetry || onReload ? (
    <>
      {onRetry ? <button className={iconButtonClass} type="button" aria-label="重试保存" title="重试保存" onClick={onRetry}><ArrowClockwise size={18} /></button> : null}
      {onReload ? <button className={iconButtonClass} type="button" aria-label="放弃草稿并重新加载" title="放弃草稿并重新加载" onClick={onReload}><ArrowsClockwise size={18} /></button> : null}
    </>
  ) : undefined;
  return (
    <InlineError
      className="mx-auto mt-4 w-[calc(100%-2rem)] max-w-[560px]"
      role="status"
      persona="settingsSaveFailed"
      message={message}
      actions={actions}
    />
  );
}
