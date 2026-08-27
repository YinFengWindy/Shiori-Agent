import type { SettingsFormData } from "../shared/types";

export type SettingsSavePhase = "idle" | "saving" | "saved" | "restart-failed" | "error";

/** Applies one immutable update to the current settings draft. */
export type SettingsDraftUpdater = (
  mutator: (current: SettingsFormData) => SettingsFormData,
) => void;

/** Shared contract implemented by every settings domain editor. */
export type SettingsSectionEditorProps = {
  draft: SettingsFormData;
  subsectionId: string;
  updateDraft: SettingsDraftUpdater;
};
