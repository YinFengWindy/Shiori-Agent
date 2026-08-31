import type { SaveSettingsResult } from "../../../src/bridge/shared";
import type { SettingsSavePhase } from "./settingsPageTypes";

export type SettingsSaveFeedback = {
  phase: Extract<SettingsSavePhase, "saved">;
  message: string;
};

/** Converts a persisted save result into the settings-page feedback state. */
export function resolveSettingsSaveFeedback(result: SaveSettingsResult): SettingsSaveFeedback {
  return result.health.ok
    ? { phase: "saved", message: "配置已即时保存。" }
    : { phase: "saved", message: `配置已保存，但健康检查失败：${result.health.message}` };
}

/** Returns how long terminal save feedback remains visible. */
export function getSettingsFeedbackTimeoutMs(phase: SettingsSavePhase): number | null {
  if (phase === "saved") return 2200;
  if (phase === "error") return 4200;
  return null;
}

/** Returns whether the page should render its terminal save feedback. */
export function shouldShowSettingsFeedback(phase: SettingsSavePhase, message: string): boolean {
  return Boolean(getSettingsFeedbackTimeoutMs(phase) && message);
}
