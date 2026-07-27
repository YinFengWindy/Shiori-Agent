import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { RoleVoiceSettingsPanel } from "./RoleVoiceSettingsPanel";

type RoleCapabilitiesPanelProps = {
  activeRole: RoleRecord | null;
  bridgeReady: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Groups runtime-facing role capabilities away from the core profile fields. */
export function RoleCapabilitiesPanel({ activeRole, bridgeReady, roleForm, onUpdate }: RoleCapabilitiesPanelProps) {
  return (
    <div className="grid gap-4 text-sm text-[#302019]">
      <div className="grid gap-3 rounded-md border border-white/50 bg-white/75 p-5 shadow-[0_12px_30px_rgba(40,20,10,0.08)]">
        <div className="flex items-center justify-between gap-3"><span>NSFW 记忆</span><SettingsToggleCard checked={roleForm.nsfwMemoryEnabled} ariaLabel="NSFW 记忆" onChange={(checked) => onUpdate((current) => ({ ...current, nsfwMemoryEnabled: checked }))} /></div>
        <div className="flex items-center justify-between gap-3"><span>自动场景 CG</span><SettingsToggleCard checked={roleForm.autoSceneCgEnabled} ariaLabel="自动场景 CG" onChange={(checked) => onUpdate((current) => ({ ...current, autoSceneCgEnabled: checked }))} /></div>
        <div className="flex items-center justify-between gap-3"><span>桌宠</span><SettingsToggleCard checked={roleForm.desktopPetEnabled} ariaLabel="桌宠" disabled={!bridgeReady || (!activeRole?.selected_pet_package_id && !roleForm.desktopPetEnabled)} onChange={(checked) => onUpdate((current) => ({ ...current, desktopPetEnabled: checked }))} /></div>
      </div>
      <RoleVoiceSettingsPanel bridgeReady={bridgeReady} roleForm={roleForm} onUpdate={onUpdate} />
    </div>
  );
}
