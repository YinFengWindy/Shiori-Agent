import { cx } from "../shared/styles";

type SettingsToggleCardProps = {
  checked: boolean;
  disabled?: boolean;
  compact?: boolean;
  ariaLabel: string;
  onChange: (checked: boolean) => void;
};

/** Renders the reusable desktop switch control used by settings rows. */
export function SettingsToggleCard({
  checked,
  disabled = false,
  compact = false,
  ariaLabel,
  onChange,
}: SettingsToggleCardProps) {
  return (
    <button
      className={cx(
        "relative inline-flex shrink-0 appearance-none rounded-full border-0 p-0 outline-none",
        compact ? "h-6 w-11" : "h-7 w-12",
        checked ? "bg-[#79B9FF]" : "bg-[#D6DDE7]",
        disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
      )}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <span
        className={cx(
          "absolute rounded-full bg-white shadow-[0_2px_6px_rgba(15,23,42,0.18)] transition-transform",
          compact ? "left-0.5 top-0.5 h-5 w-5" : "left-0.5 top-0.5 h-6 w-6",
          checked
            ? compact
              ? "translate-x-5"
              : "translate-x-[22px]"
            : "translate-x-0",
        )}
        aria-hidden="true"
      />
    </button>
  );
}
