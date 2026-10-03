import { cx, type AccountStatusTone, type AccountStatusView } from "@yinfengwindy/shiori-sdk";

const dotTones: Record<AccountStatusTone, string> = {
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  muted: "bg-ink-faint",
};

// Only the color changes between states, so it eases instead of snapping.
const dotClass = "block h-2 w-2 shrink-0 rounded-full transition-colors duration-base ease-out-soft";

/** Dot color class for a status tone. */
export function statusDotTone(tone: AccountStatusTone) {
  return dotTones[tone];
}

/**
 * Round connection indicator. Alone, the status text is its title and
 * accessible name; with `withText` the text is shown beside it and the dot
 * itself is decorative.
 */
export function AccountStatusDot({ status, withText = false, className }: {
  status: AccountStatusView;
  withText?: boolean;
  className?: string;
}) {
  if (withText) {
    return <span className={cx("inline-flex items-center gap-2", className)}>
      <span aria-hidden="true" className={cx(dotClass, statusDotTone(status.tone))} />{status.label}
    </span>;
  }
  return <span role="img" aria-label={status.label} title={status.label}
    className={cx(dotClass, statusDotTone(status.tone), className)} />;
}
