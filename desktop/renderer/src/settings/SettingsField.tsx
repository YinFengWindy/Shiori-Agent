import type React from "react";

import { cx } from "../shared/styles";

type SettingsFieldProps = {
  label: string;
  hint?: string;
  layout?: "side" | "stack";
  children: React.ReactNode;
};

/** Renders a labeled settings row with optional supporting text. */
export function SettingsField({
  label,
  hint,
  layout = "side",
  children,
}: SettingsFieldProps) {
  const stacked = layout === "stack";
  return (
    <div className={cx(
      "grid gap-3 border-b border-[#ECEEF2] py-5 last:border-b-0",
      stacked
        ? "grid-cols-[minmax(0,1fr)]"
        : cx(
            "xl:grid-cols-[minmax(0,1fr)_minmax(240px,360px)] xl:gap-8",
            hint ? "xl:items-start" : "xl:items-center",
          ),
    )}>
      <div className="grid gap-1.5">
        <div className="text-[15px] font-medium text-[#171717]">{label}</div>
        {hint ? <div className="max-w-[680px] text-[13px] leading-6 text-[#7B7F87]">{hint}</div> : null}
      </div>
      <div className={cx("w-full", !stacked && "xl:justify-self-end")}>{children}</div>
    </div>
  );
}
