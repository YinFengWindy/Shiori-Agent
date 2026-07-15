import type { SaveSettingsResult } from "../../../src/shared";
import type { SettingsSavePhase } from "./settingsPageTypes";

export type SettingsSaveFeedback = {
  phase: Extract<SettingsSavePhase, "saved" | "restart-failed">;
  message: string;
};

/** Converts a persisted save result into the settings-page feedback state. */
export function resolveSettingsSaveFeedback(result: SaveSettingsResult): SettingsSaveFeedback {
  if (!result.restart.ok) {
    return {
      phase: "restart-failed",
      message: `配置已保存，但 Bridge 重启失败：${result.restart.lastError || "unknown error"}`,
    };
  }
  if (result.health.ok) {
    return {
      phase: "saved",
      message: "配置已保存，Bridge 已重启。",
    };
  }
  return {
    phase: "saved",
    message: `配置已保存，但健康检查失败：${result.health.message}`,
  };
}

/** Returns how long terminal save feedback remains visible. */
export function getSettingsFeedbackTimeoutMs(phase: SettingsSavePhase): number | null {
  if (phase === "saved") return 2200;
  if (phase === "restart-failed" || phase === "error") return 4200;
  return null;
}

/** Returns whether the page should render its terminal save feedback. */
export function shouldShowSettingsFeedback(phase: SettingsSavePhase, message: string): boolean {
  return Boolean(getSettingsFeedbackTimeoutMs(phase) && message);
}
