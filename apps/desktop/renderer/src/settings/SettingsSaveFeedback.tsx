import type { SettingsSavePhase } from "./settingsPageTypes";
import { shouldShowSettingsFeedback } from "./settingsSaveState";
import { InlineError } from "../shared/feedback/InlineError";
import { ArrowClockwise, ArrowsClockwise } from "@phosphor-icons/react";

import { compactIconButtonClass } from "../shared/styles";

/** Renders terminal settings save feedback above the page content (吟风 fronts it when the 看板娘 is on). */
export function SettingsSaveFeedback({
  phase,
  message,
  detail,
  onRetry,
  onReload,
}: {
  phase: SettingsSavePhase;
  message: string;
  detail?: string;
  onRetry?: () => void;
  onReload?: () => void;
}) {
  if (!shouldShowSettingsFeedback(phase, message)) return null;
  const refreshOnly = phase === "refresh-error";
  const retryLabel = refreshOnly ? "重新加载" : phase === "unknown" ? "确认保存结果" : "重试保存";
  const actions = onRetry || onReload ? (
    <>
      {onRetry ? <button className={compactIconButtonClass} type="button" aria-label={retryLabel} title={retryLabel} onClick={onRetry}><ArrowClockwise size={18} /></button> : null}
      {onReload && !refreshOnly ? <button className={compactIconButtonClass} type="button" aria-label="放弃草稿并重新加载" title="放弃草稿并重新加载" onClick={onReload}><ArrowsClockwise size={18} /></button> : null}
    </>
  ) : undefined;
  return (
    <InlineError
      className="mx-auto mt-4 w-[calc(100%-2rem)] max-w-[560px]"
      role="status"
      persona="settingsSaveFailed"
      message={message}
      detail={detail}
      actions={actions}
    />
  );
}
