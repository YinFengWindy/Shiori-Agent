import { Brain, ImageSquare, Monitor } from "@phosphor-icons/react";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { RoleVoiceSettingsPanel } from "./RoleVoiceSettingsPanel";

type RoleCapabilitiesPanelProps = {
  activeRole: RoleRecord | null;
  bridgeReady: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

type CapabilitySettingRowProps = {
  icon: typeof Brain;
  label: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  disabledStatus?: string;
  onChange: (checked: boolean) => void;
};

/** Renders one runtime feature with its current state and toggle. */
function CapabilitySettingRow({
  icon: Icon,
  label,
  description,
  checked,
  disabled = false,
  disabledStatus,
  onChange,
}: CapabilitySettingRowProps) {
  const status = disabled ? (disabledStatus ?? "不可用") : checked ? "已启用" : "未启用";

  return (
    <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 py-4 first:pt-0 last:pb-0">
      <span className="grid h-9 w-9 place-items-center rounded-md bg-[#F3F6FA] text-[#4B6B88]" aria-hidden="true">
        <Icon className="h-5 w-5" weight="duotone" />
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="font-medium text-[#182230]">{label}</span>
          <span className={disabled ? "text-xs text-[#98A2B3]" : checked ? "text-xs text-[#2E7D5B]" : "text-xs text-[#7B8794]"}>{status}</span>
        </div>
        <p className="mt-0.5 text-xs leading-5 text-[#7B8794]">{description}</p>
      </div>
      <SettingsToggleCard checked={checked} ariaLabel={label} disabled={disabled} onChange={onChange} />
    </div>
  );
}

/** Groups runtime-facing role capabilities away from the core profile fields. */
export function RoleCapabilitiesPanel({ activeRole, bridgeReady, roleForm, onUpdate }: RoleCapabilitiesPanelProps) {
  const desktopPetUnavailable = !bridgeReady || (!activeRole?.selected_pet_package_id && !roleForm.desktopPetEnabled);

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
          <CapabilitySettingRow icon={Brain} label="NSFW 记忆" description="允许角色保留成人内容相关的对话记忆。" checked={roleForm.nsfwMemoryEnabled} onChange={(checked) => onUpdate((current) => ({ ...current, nsfwMemoryEnabled: checked }))} />
          <CapabilitySettingRow icon={ImageSquare} label="自动场景 CG" description="在合适的剧情节点生成场景画面。" checked={roleForm.autoSceneCgEnabled} onChange={(checked) => onUpdate((current) => ({ ...current, autoSceneCgEnabled: checked }))} />
          <CapabilitySettingRow icon={Monitor} label="桌宠" description="让角色以桌面宠物形式陪伴和互动。" checked={roleForm.desktopPetEnabled} disabled={desktopPetUnavailable} disabledStatus={!bridgeReady ? "桌面服务不可用" : "未配置桌宠"} onChange={(checked) => onUpdate((current) => ({ ...current, desktopPetEnabled: checked }))} />
        </div>
      </section>
      <RoleVoiceSettingsPanel roleForm={roleForm} onUpdate={onUpdate} />
    </div>
  );
}
