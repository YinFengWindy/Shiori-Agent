import type { SettingsSavePhase } from "./settingsPageTypes";

/** Returns whether the page should render its terminal save feedback. */
export function shouldShowSettingsFeedback(phase: SettingsSavePhase, message: string): boolean {
  return phase === "error" && Boolean(message);
}

/** How long the "已保存" confirmation lingers after the last completed save. */
export const settingsSavedIndicatorMs = 1600;

/**
 * Whether a phase change is a save that just completed successfully
 * (saving → idle). A failed save goes saving → error instead, and a reload
 * resets to idle without passing through saving, so neither counts.
 */
export function isSettingsSaveCompleted(previous: SettingsSavePhase, next: SettingsSavePhase): boolean {
  return previous === "saving" && next === "idle";
}
