import type React from "react";
import { useState } from "react";
import { SettingsField } from "./SettingsField";
import { SettingsToggleCard } from "./SettingsToggleCard";
import { cx, ghostButtonClass, inputClass } from "../shared/styles";

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
      <div className="flex w-full justify-end">
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
      <input
        className={cx(inputClass, "flex-1 bg-white")}
        type={visible ? "text" : "password"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <button
        className={cx("text-sm", ghostButtonClass)}
        type="button"
        onClick={() => setVisible((current) => !current)}
      >
        {visible ? "隐藏" : "显示"}
      </button>
    </div>
  );
}

/** Groups the fields belonging to one settings subsection. */
export function SettingsSectionCard({ children }: { children: React.ReactNode }) {
  return <section className="grid">{children}</section>;
}
