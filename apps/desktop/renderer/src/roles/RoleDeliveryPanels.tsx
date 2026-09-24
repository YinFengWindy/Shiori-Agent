import type { RoleFormState } from "../shared/types";
import { RoleChannelBindingsPanel } from "./RoleChannelBindingsPanel";
import { RoleProactiveSettingsPanel } from "./RoleProactiveSettingsPanel";
import { useRoleChannelCatalog } from "./useRoleChannelCatalog";
import { useSettingsSnapshot } from "./useSettingsSnapshot";

type RoleDeliveryPanelsProps = {
  activeRoleId: string;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
  /** Opens 设置 › 插件 on the providing plugin's own tab (null: the plugin list). */
  onOpenPluginSettings: (pluginId: string | null) => void;
};

/** The role's delivery tab: channel bindings and proactive push, sharing one live channel catalog. */
export function RoleDeliveryPanels({ activeRoleId, roleForm, onUpdate, onOpenPluginSettings }: RoleDeliveryPanelsProps) {
  const channels = useRoleChannelCatalog();
  const settings = useSettingsSnapshot();
  const bindings = roleForm.channelBindings ?? [];
  return (
    <div className="grid gap-7">
      <RoleChannelBindingsPanel activeRoleId={activeRoleId} bindings={bindings} channels={channels} onUpdate={onUpdate} onOpenPluginSettings={onOpenPluginSettings} />
      <RoleProactiveSettingsPanel bindings={bindings} channels={channels} devMode={settings?.advanced.devMode === true} roleForm={roleForm} onUpdate={onUpdate} />
    </div>
  );
}
