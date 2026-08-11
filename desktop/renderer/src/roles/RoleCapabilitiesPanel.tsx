import { Brain } from "@phosphor-icons/react";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { RoleVoiceSettingsPanel } from "./RoleVoiceSettingsPanel";
import { RoleCapabilitySettingRow } from "./RoleCapabilitySettingRow";
import { PluginRoleCapabilityHost } from "../plugins/PluginRoleCapabilityHost";

type RoleCapabilitiesPanelProps = {
  activeRole: RoleRecord | null;
  bridgeReady: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Groups runtime-facing role capabilities away from the core profile fields. */
export function RoleCapabilitiesPanel({ activeRole, bridgeReady, roleForm, onUpdate }: RoleCapabilitiesPanelProps) {
  return (
    <div className="grid gap-8 text-sm text-[#1F2937]">
      <section aria-labelledby="role-capabilities-heading">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-[#182230]" id="role-capabilities-heading">运行能力</h2>
            <p className="mt-1 text-xs text-[#7B8794]">控制角色在对话和桌面中的表现。</p>
          </div>
        </div>
        <div className="divide-y divide-[#E7ECF1] border-y border-[#E7ECF1]">
          <RoleCapabilitySettingRow icon={Brain} label="NSFW 记忆" description="允许角色保留成人内容相关的对话记忆。" checked={roleForm.nsfwMemoryEnabled} onChange={(checked) => onUpdate((current) => ({ ...current, nsfwMemoryEnabled: checked }))} />
          <PluginRoleCapabilityHost activeRole={activeRole} bridgeReady={bridgeReady} roleForm={roleForm} onUpdate={onUpdate} />
        </div>
      </section>
      <RoleVoiceSettingsPanel roleForm={roleForm} onUpdate={onUpdate} />
    </div>
  );
}
