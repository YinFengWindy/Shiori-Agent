import { cx } from "../shared/styles";
import type { AccountSnapshot } from "./accountClient";
import { accountStatus } from "./accountPresentation";

const dotTones = {
  online: "bg-success",
  connecting: "bg-warning",
  login_required: "bg-warning",
  error: "bg-danger",
  offline: "bg-ink-faint",
  unknown: "bg-ink-faint",
} as const;

const dotClass = "block h-2.5 w-2.5 shrink-0 rounded-full ring-2 ring-surface";

/** Dot color for an account; one whose plugin is not running reads as offline. */
export function accountStatusDotTone(account: Pick<AccountSnapshot, "runtimeActive" | "connection">) {
  return dotTones[account.runtimeActive ? account.connection : "offline"];
}

/**
 * Round connection indicator, ringed in the surface color so it reads over a
 * channel icon. Alone, the status text is its title and accessible name; with
 * `withText` the text is shown beside it and the dot itself is decorative.
 */
export function AccountStatusDot({ account, withText = false, className }: {
  account: AccountSnapshot;
  withText?: boolean;
  className?: string;
}) {
  const label = accountStatus(account);
  if (withText) {
    return <span className={cx("inline-flex items-center gap-1.5", className)}>
      <span aria-hidden="true" className={cx(dotClass, accountStatusDotTone(account))} />{label}
    </span>;
  }
  return <span role="img" aria-label={label} title={label}
    className={cx(dotClass, accountStatusDotTone(account), className)} />;
}
