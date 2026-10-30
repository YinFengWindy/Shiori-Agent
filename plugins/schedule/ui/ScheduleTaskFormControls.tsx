import { cx } from "@yinfengwindy/shiori-sdk";

/** Label column of one task form field. */
export const scheduleFieldLabelClass = "grid min-w-0 grid-cols-[minmax(0,1fr)] gap-1.5 text-xs text-ink-muted";

/** Renders one inline task-form validation message. */
export function ScheduleFieldError({ message }: { message?: string }) {
  return message ? <span className="text-[11px] text-danger-text">{message}</span> : null;
}

/** Renders a compact single-choice control for task form enums. */
export function ScheduleSegmentedControl<Value extends string>({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string;
  value: Value;
  options: readonly { label: string; value: Value }[];
  disabled: boolean;
  onChange: (value: Value) => void;
}) {
  return (
    // Wraps whole options onto the next row when the panel is narrow, instead
    // of breaking a label mid-word.
    <div
      className="flex min-w-0 flex-wrap gap-1 rounded-md bg-surface-soft p-1"
      role="group"
      aria-label={label}
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            className={cx(
              "h-8 grow basis-[4.25rem] whitespace-nowrap rounded-md px-2 text-[11px] font-medium transition-colors disabled:cursor-default disabled:opacity-50",
              selected ? "bg-gradient-accent text-ink shadow-soft" : "text-ink-muted hover:bg-white/70 hover:text-ink-secondary",
            )}
            type="button"
            aria-pressed={selected}
            disabled={disabled}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
