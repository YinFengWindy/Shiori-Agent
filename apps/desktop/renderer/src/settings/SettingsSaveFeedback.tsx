import type { SettingsSavePhase } from "./settingsPageTypes";
import { shouldShowSettingsFeedback } from "./settingsSaveState";
import { cx } from "../shared/styles";

/** Renders terminal settings save feedback above the page content. */
export function SettingsSaveFeedback({
  phase,
  message,
}: {
  phase: SettingsSavePhase;
  message: string;
}) {
  if (!shouldShowSettingsFeedback(phase, message)) return null;
  return (
    <div
      className={cx(
        "pointer-events-none absolute left-1/2 top-4 z-20 max-w-[560px] -translate-x-1/2 rounded-[14px] border px-4 py-2.5 text-sm leading-6 shadow-[0_16px_40px_rgba(15,23,42,0.12)] backdrop-blur-[8px]",
        phase === "saved"
          ? "border-[rgba(26,106,58,0.18)] bg-[rgba(237,248,240,0.94)] text-[#1a6a3a]"
          : "border-[rgba(176,58,58,0.18)] bg-[rgba(255,241,241,0.96)] text-[#9a2f2f]",
      )}
      role="status"
      aria-live="polite"
    >
      {message}
    </div>
  );
}
