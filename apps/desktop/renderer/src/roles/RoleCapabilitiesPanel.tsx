import { PluginRoleSettingsSlot } from "../plugins/PluginRoleSettingsSlot";
import { Brain } from "@phosphor-icons/react";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { RoleCapabilityCard } from "./RoleCapabilityCard";
import { globalVoiceOutputEnabled, roleToggleStatus } from "./roleCapabilityStatus";
import { RoleEditorSection } from "./RoleEditorSection";
import { RoleVoiceSettingsPanel } from "./RoleVoiceSettingsPanel";
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
          <PluginRoleSettingsSlot drafts={roleForm.pluginSettings} snapshots={activeRole?.plugin_state} disabled={!bridgeReady}
            onChange={(pluginSettings) => onUpdate((current) => ({ ...current, pluginSettings }))} />
        </div>
      </RoleEditorSection>
      <RoleEditorSection title="声音">
        <RoleVoiceSettingsPanel roleForm={roleForm} globalVoiceEnabled={globalVoiceOutputEnabled(settings)} onUpdate={onUpdate} />
      </RoleEditorSection>
    </div>
  );
}
