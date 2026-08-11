import { AdvancedSettingsSection } from "./AdvancedSettingsSection";
import { ChannelsSettingsSection } from "./ChannelsSettingsSection";
import { MemorySettingsSection } from "./MemorySettingsSection";
import { ModelsSettingsSection } from "./ModelsSettingsSection";
import { VoiceSettingsSection } from "./VoiceSettingsSection";
import type { SettingsSectionId } from "./SettingsSidebar";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";
import { PluginSettingsHost } from "../plugins/PluginSettingsHost";

type SettingsSectionContentProps = SettingsSectionEditorProps & {
  sectionId: SettingsSectionId;
};

/** Routes the active settings domain to its focused editor component. */
export function SettingsSectionContent({
  sectionId,
  ...editorProps
}: SettingsSectionContentProps) {
  switch (sectionId) {
    case "models":
      return <ModelsSettingsSection {...editorProps} />;
    case "channels":
      return <ChannelsSettingsSection {...editorProps} />;
    case "memory":
      return <MemorySettingsSection {...editorProps} />;
    case "integrations":
      return <PluginSettingsHost {...editorProps} />;
    case "voice":
      return <VoiceSettingsSection {...editorProps} />;
    case "advanced":
      return <AdvancedSettingsSection {...editorProps} />;
  }
}
