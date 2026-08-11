import type { SettingsSectionEditorProps } from "../settings/settingsPageTypes";
import { PluginHost } from "./PluginHost";
import { pluginContributionKey } from "./pluginCatalog";
import { PluginSettingsSchemaForm } from "./PluginSettingsSchemaForm";

/** Renders one loaded plugin's settings contribution through a built-in adapter. */
export function PluginSettingsHost(props: SettingsSectionEditorProps) {
  return <PluginHost slot="settings" render={({ plugin, contribution }) => {
    if (pluginContributionKey(plugin.plugin_id, contribution.id) !== props.subsectionId) return null;
    if (contribution.renderer !== "schema.settings" || !contribution.settings_schema?.length) return null;
    return <PluginSettingsSchemaForm {...props} schema={contribution.settings_schema} />;
  }} />;
}
