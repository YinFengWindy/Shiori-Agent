import type { ReactNode, Ref } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { XIcon } from "@phosphor-icons/react";
import { compactIconButtonClass, cx, dialogBackdropClass } from "../styles";

/**
 * The centred popup surface of a titled, scrolling dialog: fixed in the
 * middle of the window, height-capped so the body scrolls, fading and scaling
 * with `motion-dialog`. Width is added by `DialogFrame` (`wide`).
 */
const dialogPopupFrameClass =
  "confirm-dialog motion-dialog fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col gap-5 rounded-md border border-line bg-surface p-6 shadow-panel";

type DialogFrameProps = {
  /** Content of `Dialog.Title`. */
  title: ReactNode;
  /** Accessible name of the close button. */
  closeLabel: string;
  /** Blocks closing through the button, e.g. while an action is in flight. */
  closeDisabled?: boolean;
  /** Shown before the title, e.g. an avatar; the title row then centres vertically. */
  leading?: ReactNode;
  /** A line under the title. */
  subtitle?: ReactNode;
  /** Separates the title row from the body with a rule. */
  divided?: boolean;
  /** 42rem instead of the default 40rem. */
  wide?: boolean;
  /** Layout of the scrolling body (it only owns the scrolling). */
  bodyClassName?: string;
  /** Fixed row under the scrolling body, e.g. the dialog's actions. */
  footer?: ReactNode;
  /** Keeps the popup mounted (hidden) while closed; see Base UI `Dialog.Portal`. */
  keepMounted?: boolean;
  popupRef?: Ref<HTMLDivElement>;
  children?: ReactNode;
};

/**
 * One frame for the host's titled dialogs and the SDK's capability settings
 * dialog (#719): portal, backdrop, popup surface, a title row with a compact
 * close button, a scrolling body and an optional fixed footer. Render it
 * inside a Base UI `Dialog.Root`. Host-only (`host-internal`), not part of
 * the plugin contract.
 */
export function DialogFrame({ title, closeLabel, closeDisabled, leading, subtitle, divided, wide, bodyClassName, footer, keepMounted, popupRef, children }: DialogFrameProps) {
  return (
    <Dialog.Portal keepMounted={keepMounted}>
      <Dialog.Backdrop className={dialogBackdropClass} />
      <Dialog.Popup ref={popupRef} className={cx(dialogPopupFrameClass, wide ? "w-[min(42rem,calc(100vw-2rem))]" : "w-[min(40rem,calc(100vw-2rem))]")}>
        <div className={cx("flex shrink-0 justify-between gap-4", leading ? "items-center" : "items-start", divided && "border-b border-line-soft pb-4")}>
          <div className="flex min-w-0 items-center gap-3">
            {leading}
            <div className="grid min-w-0 gap-0.5">
              <Dialog.Title className="m-0 min-w-0 break-words font-display text-title font-semibold text-ink">{title}</Dialog.Title>
              {subtitle ? <p className="m-0 truncate text-body-sm text-ink-muted">{subtitle}</p> : null}
            </div>
          </div>
          <Dialog.Close className={compactIconButtonClass} aria-label={closeLabel} disabled={closeDisabled}>
            <XIcon className="h-4 w-4" weight="bold" aria-hidden="true" />
          </Dialog.Close>
        </div>
        <div className={cx("scrollbar-stable min-h-0 overflow-y-auto overscroll-contain", bodyClassName)} data-dialog-body="">
          {children}
        </div>
        {footer}
      </Dialog.Popup>
    </Dialog.Portal>
  );
}
