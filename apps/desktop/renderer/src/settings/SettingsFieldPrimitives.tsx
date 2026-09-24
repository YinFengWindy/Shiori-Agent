import type React from "react";
import { useState } from "react";
import { Eye, EyeSlash } from "@phosphor-icons/react";
import { SettingsField } from "./SettingsField";
import { SettingsToggleCard } from "./SettingsToggleCard";
import { parseSettingsNumber } from "./settingsSectionUtils";
import { cardClass, compactPressableClass, cx } from "../shared/styles";

/** Shared compact field styling for editable settings values. */
export const settingsInputClass = "w-full rounded-md border border-line bg-surface-soft px-2.5 py-2 text-body-sm text-ink transition placeholder:text-ink-faint hover:border-line-strong focus:bg-surface";

/** Shared icon-only action styling for compact settings controls. */
export const settingsIconButtonClass = cx(compactPressableClass, "grid h-8 w-8 shrink-0 place-items-center rounded-md text-ink-muted hover:bg-surface-hover hover:text-ink");

/** Renders a settings row containing the shared toggle control. */
export function SettingsToggleField({
  label,
  hint,
  configKey,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  hint?: string;
  configKey?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <SettingsField label={label} hint={hint} configKey={configKey}>
      <div className="flex w-full items-center justify-end">
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
  ariaLabel,
  autoFocus,
  onBlur,
}: {
  value: string;
  onChange: (value: string) => void;
  ariaLabel?: string;
  autoFocus?: boolean;
  onBlur?: () => void;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="flex items-center gap-2">
      <input aria-label={ariaLabel} className={cx(settingsInputClass, "min-w-0 flex-1")} type={visible ? "text" : "password"} autoComplete="off" spellCheck={false} autoFocus={autoFocus} value={value} onBlur={onBlur} onChange={(event) => onChange(event.target.value)} />
      <button
        className={settingsIconButtonClass}
        type="button"
        onClick={() => setVisible((current) => !current)}
        aria-label={visible ? "隐藏密钥" : "显示密钥"}
        title={visible ? "隐藏密钥" : "显示密钥"}
      >
        {visible ? <EyeSlash className="h-3.5 w-3.5" weight="bold" /> : <Eye className="h-3.5 w-3.5" weight="bold" />}
      </button>
    </div>
  );
}

/**
 * Numeric settings input with an optional unit suffix. Keeps the last valid
 * number while the text is momentarily unparsable (same rule as
 * `parseSettingsNumber`).
 */
export function SettingsNumberInput({
  value,
  onChange,
  unit,
  ariaLabel,
  min,
  max,
}: {
  value: number;
  onChange: (value: number) => void;
  unit?: string;
  ariaLabel: string;
  min?: number;
  max?: number;
}) {
  return (
    <div className="relative flex items-center">
      <input
        aria-label={ariaLabel}
        className={cx(settingsInputClass, "tabular-nums", unit && "pr-14")}
        inputMode="decimal"
        // A textbox cannot carry aria-value*; the accepted range is a hover hint and the backend validates.
        title={min !== undefined || max !== undefined ? `${min ?? "…"} – ${max ?? "…"}` : undefined}
        value={String(value)}
        onChange={(event) => onChange(parseSettingsNumber(event.target.value, value))}
      />
      {unit ? <span className="pointer-events-none absolute right-3 text-caption text-ink-muted" aria-hidden="true">{unit}</span> : null}
    </div>
  );
}

/** Groups the fields belonging to one settings subsection into a card. */
export function SettingsSectionCard({ children }: { children: React.ReactNode }) {
  return <section className={cx(cardClass, "grid px-4 sm:px-5")}>{children}</section>;
}

/** A titled card: one topic within a settings page that has several. */
export function SettingsGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-2.5" aria-label={title}>
      <h3 className="m-0 px-1 text-body-sm font-semibold text-ink-secondary">{title}</h3>
      <div className={cx(cardClass, "grid px-4 sm:px-5")}>{children}</div>
    </section>
  );
}

/** Vertical rhythm between the titled groups of one settings page. */
export const settingsGroupStackClass = "grid gap-7";
