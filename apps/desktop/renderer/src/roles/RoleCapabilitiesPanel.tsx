import { PluginRoleSettingsSlot } from "../plugins/PluginRoleSettingsSlot";
import { Brain, Chats } from "@phosphor-icons/react";
import {
  SettingsToggleCard,
  type RoleRecord,
  RoleCapabilityCard,
  roleToggleStatus,
} from "@yinfengwindy/shiori-sdk";
import type { RoleFormState } from "../shared/types";
import { RoleEditorSection } from "./RoleEditorSection";
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
            icon={<Chats className="h-5 w-5" weight="duotone" />}
            title="自然聊天"
            status={roleToggleStatus(roleForm.naturalChatEnabled)}
            control={<SettingsToggleCard checked={roleForm.naturalChatEnabled} ariaLabel="自然聊天" onChange={(checked) => onUpdate((current) => ({ ...current, naturalChatEnabled: checked }))} />}
          />
          <RoleCapabilityCard
            icon={<Brain className="h-5 w-5" weight="duotone" />}
            title="NSFW 记忆"
            status={roleToggleStatus(roleForm.nsfwMemoryEnabled)}
            control={<SettingsToggleCard checked={roleForm.nsfwMemoryEnabled} ariaLabel="NSFW 记忆" onChange={(checked) => onUpdate((current) => ({ ...current, nsfwMemoryEnabled: checked }))} />}
          />
          <PluginRoleSettingsSlot roleId={activeRole?.id ?? null} moodCatalog={roleForm.moodCatalog} drafts={roleForm.pluginSettings} snapshots={activeRole?.plugin_state} disabled={!bridgeReady} devMode={settings?.advanced.devMode === true}
            onChange={(pluginSettings) => onUpdate((current) => ({ ...current, pluginSettings }))} />
        </div>
      </RoleEditorSection>
    </div>
  );
}
