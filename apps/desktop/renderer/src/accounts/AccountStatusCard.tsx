import { PlugIcon, StopIcon } from "@phosphor-icons/react";
import {
  type AccountStatusCardAction,
  type AccountStatusCardProps,
  cardClass,
  compactGhostButtonClass,
  cx,
  type AccountPendingAction,
} from "@shiori/plugin-sdk";
import { InlineError } from "../shared/feedback/InlineError";
import { SpinnerIcon } from "../shared/icons";
import { compactPrimaryButtonClass } from "../shared/styles";
import { Reveal } from "../shared/ui/Reveal";
import { accountCardActionLabels, accountCardView } from "@shiori/plugin-sdk/host-internal";
import { AccountStatusDot } from "./AccountStatusDot";

/**
 * One account's connection at a glance, the same for every channel: status
 * dot and words with short progress on the left, the single connect /
 * disconnect action on the right, and plugin rows (QR code, progress) below.
 * The host's own failure report shows here too.
 */
export function AccountStatusCard({ account, status, pending = null, detail, action, children }: AccountStatusCardProps) {
  // The wording is the SDK's, shared with the testing entry's stand-in card.
  const { status: shown, failure } = accountCardView({ account, status, pending });
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
    {accountCardActionLabels[action.kind]}
  </button>;
}
