import { cx, focusResetClass } from "../shared/styles";

/** Shared field styling for task form controls. */
export const roleTaskFieldClass =
  "w-full rounded-md border border-[#D8DFE7] bg-white px-3 py-2.5 text-sm text-[#344054] transition focus:border-[#B8C2CE] focus:outline-none disabled:opacity-60";

/** Shared label styling for task form fields. */
export const roleTaskFieldLabelClass = "grid gap-1.5 text-xs text-[#667085]";

/** Renders one inline task-form validation message. */
export function RoleTaskFieldError({ message }: { message?: string }) {
  return message ? <span className="text-[11px] text-[#B42318]">{message}</span> : null;
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
    <div
      className={cx(
        "grid gap-1 rounded-md bg-[#E9EDF2] p-1",
        options.length === 2 ? "grid-cols-2" : "grid-cols-3",
      )}
      role="group"
      aria-label={label}
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            className={cx(
              "h-8 rounded-md px-2 text-[11px] font-medium transition-colors disabled:cursor-default disabled:opacity-50",
              selected ? "bg-[#272536] text-white shadow-[0_2px_6px_rgba(39,37,54,0.14)]" : "text-[#667085] hover:bg-white/70 hover:text-[#344054]",
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
