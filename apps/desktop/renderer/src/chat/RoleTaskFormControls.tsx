import { cx, focusResetClass } from "../shared/styles";

/** Shared field styling for task form controls. */
export const roleTaskFieldClass =
  "w-full min-w-0 rounded-md border border-line-soft bg-white px-2.5 py-2.5 text-sm text-ink-secondary transition focus:border-line focus:outline-none disabled:opacity-60";

/** Shared label styling for task form fields. */
export const roleTaskFieldLabelClass = "grid min-w-0 grid-cols-[minmax(0,1fr)] gap-1.5 text-xs text-ink-muted";

/** Renders one inline task-form validation message. */
export function RoleTaskFieldError({ message }: { message?: string }) {
  return message ? <span className="text-[11px] text-danger-text">{message}</span> : null;
}

/** Renders a compact single-choice control for task form enums. */
export function RoleTaskSegmentedControl<Value extends string>({
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
              focusResetClass,
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
