import { PlugIcon, StopIcon } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { InlineError } from "../shared/feedback/InlineError";
import { SpinnerIcon } from "../shared/icons";
import { cardClass, compactGhostButtonClass, compactPrimaryButtonClass, cx } from "../shared/styles";
import { Reveal } from "../shared/ui/Reveal";
import type { AccountSnapshot } from "./accountClient";
import {
  accountStatusView, pendingAccountStatus, type AccountPendingAction, type AccountStatusView,
} from "./accountPresentation";
import { AccountStatusDot } from "./AccountStatusDot";

/** The card's one button: 连接 while the account is offline, 断开连接 while it runs. */
export type AccountStatusCardAction = {
  kind: "connect" | "disconnect";
  onClick: () => void;
  /** Blocks the button for a plugin reason (missing credentials, not supported here). */
  disabled?: boolean;
};

/** Props of `AccountStatusCard` (plugins get it as `PluginHostServices.ui.AccountStatusCard`). */
export type AccountStatusCardProps = {
  /** The host account, or null while a new one is being added. */
  account: AccountSnapshot | null;
  /** A plugin-known status (e.g. a QR login step) that replaces the host's reading of `account`. */
  status?: AccountStatusView;
  /** A request in flight: its status shows at once and its button spins; every button waits. */
  pending?: AccountPendingAction | null;
  /** Short progress under the status, e.g. `NapCat v4 · 下载中 42%`. */
  detail?: ReactNode;
  action?: AccountStatusCardAction;
  /** Rows below the status (QR code, progress bar); wrap each changing row in `Reveal`. */
  children?: ReactNode;
};

const actionLabels = { connect: "连接", disconnect: "断开连接" } as const;

/**
 * One account's connection at a glance, the same for every channel: status
 * dot and words with short progress on the left, the single connect /
 * disconnect action on the right, and plugin rows (QR code, progress) below.
 * The host's own failure report shows here too.
 */
export function AccountStatusCard({ account, status, pending = null, detail, action, children }: AccountStatusCardProps) {
  const shown = pending ? pendingAccountStatus(pending) : status ?? (account ? accountStatusView(account) : { label: "未连接", tone: "muted" as const });
  const failure = !pending && account?.connection === "error" ? account.error : "";
  return <section className={cx(cardClass, "p-4")} aria-label="连接状态">
    <div className="flex items-center justify-between gap-3">
      <div className="grid min-w-0" aria-live="polite">
        <AccountStatusDot status={shown} withText className="text-body font-medium text-ink" />
        <Reveal show={Boolean(detail)} className="pt-0.5 text-body-sm text-ink-muted">{detail}</Reveal>
      </div>
      {action ? <AccountStatusCardButton action={action} pending={pending} /> : null}
    </div>
    <Reveal show={Boolean(failure)} className="pt-3"><InlineError message={failure} /></Reveal>
    {children}
  </section>;
}

function AccountStatusCardButton({ action, pending }: { action: AccountStatusCardAction; pending: AccountPendingAction | null }) {
  const acting = pending === action.kind;
  const Icon = action.kind === "connect" ? PlugIcon : StopIcon;
  return <button type="button" className={action.kind === "connect" ? compactPrimaryButtonClass : compactGhostButtonClass}
    disabled={Boolean(pending) || action.disabled} aria-busy={acting || undefined} onClick={action.onClick}>
    {acting
      ? <SpinnerIcon className="h-4 w-4 animate-spin stroke-current motion-reduce:animate-none" />
      : <Icon className="h-4 w-4" aria-hidden="true" />}
    {actionLabels[action.kind]}
  </button>;
}
