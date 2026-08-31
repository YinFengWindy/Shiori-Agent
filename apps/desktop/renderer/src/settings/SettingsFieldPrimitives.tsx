import type React from "react";
import { useState } from "react";
import { Eye, EyeSlash } from "@phosphor-icons/react";
import { SettingsField } from "./SettingsField";
import { SettingsToggleCard } from "./SettingsToggleCard";
import { cx } from "../shared/styles";

/** Shared compact field styling for editable settings values. */
export const settingsInputClass = "w-full rounded-md border border-[#D8DCE2] bg-[#F7F9FB] px-3 py-2.5 text-sm text-[#182230] transition placeholder:text-[#98A2B3] focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20";

/** Renders a settings row containing the shared toggle control. */
export function SettingsToggleField({
  label,
  hint,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <SettingsField label={label} hint={hint}>
      <div className="flex w-full items-center justify-end gap-3">
        <span className={checked ? "text-xs text-accent-deep" : "text-xs text-[#98A2B3]"}>{checked ? "已启用" : "未启用"}</span>
        <SettingsToggleCard
          checked={checked}
          disabled={disabled}
          ariaLabel={label}
          onChange={onChange}
        />
      </div>
    </SettingsField>
  );
}

/** Renders a password input whose value can be revealed locally. */
export function SettingsSecretInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="flex items-center gap-3">
      <input className={cx(settingsInputClass, "flex-1")} type={visible ? "text" : "password"} value={value} onChange={(event) => onChange(event.target.value)} />
      <button
        className="grid h-9 w-9 place-items-center rounded-md text-[#667085] transition hover:bg-[#F3F6FA] hover:text-[#182230] focus:outline-none focus:ring-2 focus:ring-primary/20"
        type="button"
        onClick={() => setVisible((current) => !current)}
        aria-label={visible ? "隐藏密钥" : "显示密钥"}
        title={visible ? "隐藏密钥" : "显示密钥"}
      >
        {visible ? <EyeSlash className="h-4 w-4" weight="bold" /> : <Eye className="h-4 w-4" weight="bold" />}
      </button>
    </div>
  );
}

/** Groups the fields belonging to one settings subsection into a card. */
export function SettingsSectionCard({ children }: { children: React.ReactNode }) {
  return <section className="grid rounded-md border border-stroke bg-white px-5 sm:px-6">{children}</section>;
}
