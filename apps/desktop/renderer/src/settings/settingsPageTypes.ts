import type { DraftSavePhase } from "../shared/serialDraftQueue";
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

/** Props for a settings section that owns its own data (no shared draft). */
export type StandaloneSettingsSectionProps = {
  subsectionId: string;
  /**
   * Opens another subsection of the same section — how 「插件」's list
   * reaches a plugin's nested settings page. Absent where a component is
   * mounted outside `SettingsPage`.
   */
  onSelectSubsection?: (subsectionId: string) => void;
};
