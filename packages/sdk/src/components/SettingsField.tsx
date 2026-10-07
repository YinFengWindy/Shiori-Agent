import type { ReactNode } from "react";
import { cardClass, cx } from "../styles";
import { SettingsToggleCard } from "./SettingsToggleCard";

/** Props of `SettingsField`, one labeled row of a settings page. */
export type SettingsFieldProps = {
  label: ReactNode;
  hint?: string;
  /**
   * The raw config key behind a translated label (e.g. `max_tokens`), shown
   * small and muted so it stays findable in config.toml and docs.
   */
  configKey?: string;
  /** `side` puts the control to the right of the label on wide screens; `stack` below it. */
  layout?: "side" | "stack";
  /** Tighter rows for fields hosted in a small floating card (first-run setup). */
  dense?: boolean;
  children: ReactNode;
};

/** Renders a labeled settings row with optional supporting text, as on the host's settings pages. */
export function SettingsField({
  label,
  hint,
  configKey,
  layout = "side",
  dense = false,
  children,
}: SettingsFieldProps) {
  const stacked = layout === "stack";
  return (
    <div className={cx(
      "grid border-b border-line-soft last:border-b-0",
      dense ? "gap-2 py-3.5" : "gap-3 py-5",
      stacked
        ? "grid-cols-[minmax(0,1fr)]"
        : cx(
            "xl:grid-cols-[minmax(0,1fr)_minmax(240px,360px)] xl:gap-8",
            hint || configKey ? "xl:items-start" : "xl:items-center",
          ),
    )}>
      <div className="grid min-w-0 gap-1">
        <div className="text-body-sm font-medium text-ink">{label}</div>
        {configKey ? <code className="w-fit break-all font-mono text-caption text-ink-muted">{configKey}</code> : null}
        {hint ? <div className="max-w-[680px] text-caption text-ink-muted">{hint}</div> : null}
      </div>
      <div className={cx("w-full", !stacked && "xl:justify-self-end")}>{children}</div>
    </div>
  );
}

/** Props of `SettingsToggleField`, a settings row whose control is the shared switch. */
export type SettingsToggleFieldProps = {
  /** Row label, also the switch's accessible name. */
  label: string;
  hint?: string;
  configKey?: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (checked: boolean) => void;
};

/** Renders a settings row containing the shared toggle control. */
export function SettingsToggleField({ label, hint, configKey, checked, disabled, onChange }: SettingsToggleFieldProps) {
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

/** Groups the fields belonging to one settings subsection into a card. */
export function SettingsSectionCard({ children }: { children: ReactNode }) {
  return <section className={cx(cardClass, "grid px-4 sm:px-5")}>{children}</section>;
}

/** A titled card: one topic within a settings page that has several (stack them with `settingsGroupStackClass`). */
export function SettingsGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-2.5" aria-label={title}>
      <h3 className="m-0 px-1 text-body-sm font-semibold text-ink-secondary">{title}</h3>
      <div className={cx(cardClass, "grid px-4 sm:px-5")}>{children}</div>
    </section>
  );
}
