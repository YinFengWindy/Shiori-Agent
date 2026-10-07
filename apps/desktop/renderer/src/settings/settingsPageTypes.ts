import type { DraftSavePhase } from "@yinfengwindy/shiori-sdk";
import type { SettingsFormData } from "../shared/types";

/** Historical name for `DraftSavePhase`, kept for this domain's existing consumers. */
export type SettingsSavePhase = DraftSavePhase;

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

/** One tab within a settings section's sub-navigation. */
export type SettingsSubsection = {
  id: string;
  label: string;
};
