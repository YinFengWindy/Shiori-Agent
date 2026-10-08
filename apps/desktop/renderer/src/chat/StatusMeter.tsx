import React from "react";
import { cx } from "@yinfengwindy/shiori-sdk";

type StatusMeterProps = {
  label: string;
  /** Text shown opposite the label; numeric values align as tabular figures. */
  value: string | number;
  /** Fill width, already clamped to 0–100. */
  percent: number;
  /** Track height utility, e.g. `h-1` for a thin bar. */
  heightClass: string;
  testId?: string;
};

/** A labelled status row with a decorative progress track shared by the chat status sidebar. */
export function StatusMeter({ label, value, percent, heightClass, testId }: StatusMeterProps) {
  return (
    <div data-testid={testId}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-body font-semibold text-ink-muted">{label}</div>
        <div className={cx("text-body font-semibold text-ink", typeof value === "number" && "tabular-nums")}>{value}</div>
      </div>
      <div className={cx("mt-1 overflow-hidden rounded-full bg-accent-soft", heightClass)} aria-hidden="true">
        <div
          className="h-full rounded-full bg-gradient-accent-medium transition-[width] duration-300"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
