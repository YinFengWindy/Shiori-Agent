import type { ComponentProps } from "react";
import { createPortal } from "react-dom";
import { accountCardActionLabels, accountCardView } from "../account/account";
import type {
  AccountDetailActionsProps,
  AccountStatusCardProps,
  HostConfirmDialogProps,
  HostInlineErrorProps,
  PluginHostUi,
  RevealProps,
} from "../contract/hostUi";

/** The props of every render of each `host.ui` stand-in, in render order (StrictMode renders twice). */
export type FakeHostUiRenders = { [Name in keyof PluginHostUi]: Array<ComponentProps<PluginHostUi[Name]>> };

/**
 * Plain stand-ins for the host components (`host.ui`), for plugin tests.
 *
 * Each renders the parts of its contract a test observes — text, buttons and
 * their disabled / busy state, ARIA roles — without the host's styling,
 * motion or 吟风 (assert a `persona` through `renders` instead), and records
 * its props. The account status card uses the host's own status wording.
 * `AccountDetailActions` lands in a separate element, like the host's
 * account dialog danger zone, not inside the plugin's own markup.
 */
export function createFakeHostUi() {
  const renders: FakeHostUiRenders = {
    InlineError: [], ConfirmDialog: [], AccountStatusCard: [], AccountDetailActions: [], Reveal: [],
  };
  let actionsZone: HTMLElement | null = null;

  /** The element `AccountDetailActions` render into, created in the current test document on first use. */
  function accountDetailActionsZone() {
    if (!actionsZone?.isConnected) {
      actionsZone = document.createElement("div");
      actionsZone.dataset.testid = "host-account-detail-actions";
      document.body.append(actionsZone);
    }
    return actionsZone;
  }

  function InlineError(props: HostInlineErrorProps) {
    renders.InlineError.push(props);
    const { message, title, detail, actions, role = "alert", onDismiss, className, testId } = props;
    return <div role={role || undefined} className={className} data-testid={testId}>
      {title ? <strong>{title}</strong> : null}
      <p>{message}</p>
      {detail ? <p>{detail}</p> : null}
      {actions}
      {onDismiss ? <button type="button" aria-label="关闭" onClick={onDismiss} /> : null}
    </div>;
  }

  function ConfirmDialog(props: HostConfirmDialogProps) {
    renders.ConfirmDialog.push(props);
    const { open, title, description, confirmLabel, children, busy = false, confirmDisabled = false } = props;
    if (!open) return null;
    return <div role="dialog" aria-label={title}>
      <h2>{title}</h2>
      <p>{description}</p>
      {children}
      {props.error ? <p role="alert">{props.error}</p> : null}
      <button type="button" disabled={busy} onClick={props.onClose}>{props.cancelLabel ?? "取消"}</button>
      <button type="button" disabled={busy || confirmDisabled} onClick={props.onConfirm}>
        {busy ? props.busyLabel ?? confirmLabel : confirmLabel}
      </button>
    </div>;
  }

  function AccountStatusCard(props: AccountStatusCardProps) {
    renders.AccountStatusCard.push(props);
    const { account, status, pending = null, detail, action, children } = props;
    const view = accountCardView({ account, status, pending });
    return <section aria-label="连接状态">
      <div aria-live="polite"><span>{view.status.label}</span>{detail ? <div>{detail}</div> : null}</div>
      {action
        ? <button type="button" disabled={Boolean(pending) || action.disabled}
          aria-busy={pending === action.kind || undefined} onClick={action.onClick}>{accountCardActionLabels[action.kind]}</button>
        : null}
      {view.failure ? <p role="alert">{view.failure}</p> : null}
      {children}
    </section>;
  }

  function AccountDetailActions(props: AccountDetailActionsProps) {
    renders.AccountDetailActions.push(props);
    if (!props.actions.length) return null;
    return createPortal(props.actions.map(({ label, onClick, pending = false, disabled = false }) => (
      <button key={label} type="button" disabled={pending || disabled} aria-busy={pending || undefined} onClick={onClick}>{label}</button>
    )), accountDetailActionsZone());
  }

  function Reveal(props: RevealProps) {
    renders.Reveal.push(props);
    return props.show ? <div className={props.className}>{props.children}</div> : null;
  }

  const ui: PluginHostUi = { InlineError, ConfirmDialog, AccountStatusCard, AccountDetailActions, Reveal };
  return { ui, renders, accountDetailActionsZone };
}
