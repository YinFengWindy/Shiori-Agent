import type React from "react";

import { cx } from "../shared/styles";

type SettingsFieldProps = {
  label: React.ReactNode;
  hint?: string;
  /**
   * The raw config key behind a translated label (e.g. `max_tokens`), shown
   * small and muted so it stays findable in config.toml and docs.
   */
  configKey?: string;
  layout?: "side" | "stack";
  /** Tighter rows for fields hosted in a small floating card (first-run setup). */
  dense?: boolean;
  children: React.ReactNode;
};

/** Renders a labeled settings row with optional supporting text. */
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
