import { PluginRoleSettingsSlot } from "../plugins/PluginRoleSettingsSlot";
import { PluginRoleUiSlot } from "../plugins/PluginRoleUiSlot";
import { BellRinging, Brain } from "@phosphor-icons/react";
import {
  SettingsToggleCard,
  type RoleRecord,
  RoleCapabilityCard,
  roleToggleStatus,
} from "@yinfengwindy/shiori-sdk";
import type { RoleFormState } from "../shared/types";
import { RoleEditorSection } from "./RoleEditorSection";
import { roleProactiveDefaults } from "./roleProactiveDefaults";
import { RoleProactiveSettingsPanel } from "./RoleProactiveSettingsPanel";
import { useSettingsSnapshot } from "./useSettingsSnapshot";

type RoleCapabilitiesPanelProps = {
  activeRole: RoleRecord | null;
  bridgeReady: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Groups runtime-facing role capabilities away from the core profile fields. */
export function RoleCapabilitiesPanel({ activeRole, bridgeReady, roleForm, onUpdate }: RoleCapabilitiesPanelProps) {
  const settings = useSettingsSnapshot();
  const proactiveEnabled = Boolean(roleForm.proactiveEnabled ?? roleProactiveDefaults.enabled);

  return (
    <div className="grid gap-7 text-body text-ink">
      <RoleEditorSection title="运行能力">
        <div className="grid gap-4 sm:grid-cols-2">
          <RoleCapabilityCard
            icon={<Brain className="h-5 w-5" weight="duotone" />}
            title="NSFW 记忆"
            status={roleToggleStatus(roleForm.nsfwMemoryEnabled)}
            control={<SettingsToggleCard checked={roleForm.nsfwMemoryEnabled} ariaLabel="NSFW 记忆" onChange={(checked) => onUpdate((current) => ({ ...current, nsfwMemoryEnabled: checked }))} />}
          />
          <RoleCapabilityCard
            icon={<BellRinging className="h-5 w-5" weight="duotone" />}
            title="主动推送"
            status={roleToggleStatus(proactiveEnabled)}
            data-testid="role-proactive-capability"
            control={<SettingsToggleCard checked={proactiveEnabled} ariaLabel="主动推送" onChange={(checked) => onUpdate((current) => ({ ...current, proactiveEnabled: checked }))} />}
          />
          <PluginRoleSettingsSlot drafts={roleForm.pluginSettings} snapshots={activeRole?.plugin_state} disabled={!bridgeReady}
            onChange={(pluginSettings) => onUpdate((current) => ({ ...current, pluginSettings }))} />
        </div>
      </RoleEditorSection>
      <PluginRoleUiSlot role={activeRole ? { id: activeRole.id, name: activeRole.name, moodCatalog: roleForm.moodCatalog } : null} disabled={!bridgeReady} />
      <RoleProactiveSettingsPanel devMode={settings?.advanced.devMode === true} roleForm={roleForm} onUpdate={onUpdate} />
    </div>
  );
}
