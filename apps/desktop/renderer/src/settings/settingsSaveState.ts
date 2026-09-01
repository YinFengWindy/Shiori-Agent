import type { SettingsSavePhase } from "./settingsPageTypes";

/** Returns how long terminal save feedback remains visible. */
export function getSettingsFeedbackTimeoutMs(phase: SettingsSavePhase): number | null {
  if (phase === "error") return 4200;
  return null;
}

/** Returns whether the page should render its terminal save feedback. */
export function shouldShowSettingsFeedback(phase: SettingsSavePhase, message: string): boolean {
  return phase === "error" && Boolean(message);
}
