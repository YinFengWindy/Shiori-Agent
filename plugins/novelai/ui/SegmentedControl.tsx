import type { ReactNode } from "react";
import { cx } from "../../../apps/desktop/renderer/src/shared/styles";

type SegmentedOption = { value: string; label: string; badge?: ReactNode };

type SegmentedControlProps = {
  ariaLabel: string;
  options: readonly SegmentedOption[];
  value: string;
  onChange: (value: string) => void;
  size?: "sm" | "md";
};

/** Equal-width single choice in the host's segment look (same as the chat model menu's effort row). */
export function SegmentedControl({ ariaLabel, options, value, onChange, size = "sm" }: SegmentedControlProps) {
  return (
    <div
      className="grid gap-0.5 rounded-md bg-surface-soft p-0.5"
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
      role="radiogroup"
      aria-label={ariaLabel}
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            className={cx(
              "inline-flex min-w-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md transition-colors duration-quick",
              size === "md" ? "h-8 text-body-sm" : "h-7 text-caption",
              selected ? "bg-white font-medium text-ink shadow-soft" : "text-ink-muted hover:bg-white/60 hover:text-ink-secondary",
            )}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.value)}
          >
            <span className="truncate">{option.label}</span>
            {option.badge}
          </button>
        );
      })}
    </div>
  );
}
