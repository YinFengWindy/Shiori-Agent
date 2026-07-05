import type { RoleRecord, SettingsFormData } from "../shared/types";
import type { SettingsSectionId } from "./SettingsSidebar";

export type SettingsSectionContentProps = {
  section: SettingsSectionId;
  subsectionId: string;
  draft: SettingsFormData;
  roles: RoleRecord[];
  dirty: boolean;
  updateDraft: (mutator: (current: SettingsFormData) => SettingsFormData) => void;
  updateProactiveTargetChannel: (nextChannel: string) => void;
  updateProactiveTargetRoleId: (nextRoleId: string) => void;
};
