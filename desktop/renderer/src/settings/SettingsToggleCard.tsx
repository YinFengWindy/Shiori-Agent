import { cx } from "../shared/styles";

type SettingsToggleCardProps = {
  title: string;
  description?: string;
  checked: boolean;
  disabled?: boolean;
  compact?: boolean;
  onChange: (checked: boolean) => void;
};

/** Renders a reusable desktop settings toggle that matches the card-style switch treatment. */
export function SettingsToggleCard({
  title,
  description,
  checked,
  disabled = false,
  compact = false,
  onChange,
}: SettingsToggleCardProps) {
  return (
    <button
      className={cx(
        "group flex w-full items-center gap-4 rounded-[18px] border border-[#E6E9EE] bg-white text-left transition",
        compact ? "min-h-[56px] px-4 py-3" : "min-h-[72px] px-5 py-4",
        disabled
          ? "cursor-not-allowed opacity-60"
          : "cursor-pointer hover:border-[#D7DDE7] hover:bg-[#FCFCFD] focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary",
      )}
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={title}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <span className="min-w-0 flex-1">
        <span className={cx("block text-[#171717]", compact ? "text-sm font-medium" : "text-[15px] font-medium")}>
          {title}
        </span>
        {description ? (
          <span className={cx("mt-1 block text-[#7B7F87]", compact ? "text-xs leading-5" : "text-[13px] leading-6")}>
            {description}
          </span>
        ) : null}
      </span>
      <span
        className={cx(
          "relative inline-flex shrink-0 rounded-full transition-colors",
          compact ? "h-7 w-12" : "h-7 w-12",
          checked ? "bg-[#75B8FF]" : "bg-[#D7DEE8]",
        )}
        aria-hidden="true"
      >
        <span
          className={cx(
            "absolute top-0.5 h-6 w-6 rounded-full bg-white shadow-[0_2px_6px_rgba(15,23,42,0.18)] transition-transform",
            checked ? "translate-x-[22px]" : "translate-x-0.5",
          )}
        />
      </span>
    </button>
  );
}
