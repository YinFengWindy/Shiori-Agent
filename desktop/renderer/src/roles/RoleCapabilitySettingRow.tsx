import type { Icon } from "@phosphor-icons/react";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";

type RoleCapabilitySettingRowProps = {
  icon: Icon;
  label: string;
  description: string;
  checked: boolean;
  disabled?: boolean;
  disabledStatus?: string;
  onChange: (checked: boolean) => void;
};

/** Renders one role capability with availability and enabled state. */
export function RoleCapabilitySettingRow({
  icon: IconComponent,
  label,
  description,
  checked,
  disabled = false,
  disabledStatus,
  onChange,
}: RoleCapabilitySettingRowProps) {
  const status = disabled ? (disabledStatus ?? "不可用") : checked ? "已启用" : "未启用";
  return (
    <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 py-4 first:pt-0 last:pb-0">
      <span className="grid h-9 w-9 place-items-center rounded-md bg-[#F3F6FA] text-[#4B6B88]" aria-hidden="true">
        <IconComponent className="h-5 w-5" weight="duotone" />
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
