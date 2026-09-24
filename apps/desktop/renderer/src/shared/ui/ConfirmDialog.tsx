import { useState, type ReactNode } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { dangerButtonClass, ghostButtonClass, primaryButtonClass } from "../styles";

/** Accessible confirmation shell with a non-dismissable in-flight action. */
export function ConfirmDialog({ open, title, description, confirmLabel, children, busy = false, busyLabel = "删除中...", cancelLabel = "取消", error = "", destructive = true, finalFocus, onClose, onConfirm }: {
  open: boolean; title: string; description: string; confirmLabel: string; children?: ReactNode;
  busy?: boolean; busyLabel?: string; cancelLabel?: string; error?: string; destructive?: boolean; onClose: () => void; onConfirm: () => void;
  /** Optional stable focus destination when a successful action removes its trigger. */
  finalFocus?: Dialog.Popup.Props["finalFocus"];
}) {
  // Callers usually derive the copy from the pending item and clear it on
  // close; keep showing the last open copy so the exit animation does not
  // play on an emptied, resized dialog.
  const [shown, setShown] = useState({ title, description, children });
  if (open && (shown.title !== title || shown.description !== description || shown.children !== children)) {
    setShown({ title, description, children });
  }
  const content = open ? { title, description, children } : shown;
  return <Dialog.Root open={open} onOpenChange={(next) => { if (!next && !busy) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Backdrop className="confirm-dialog-backdrop motion-backdrop fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm" />
      <Dialog.Popup finalFocus={finalFocus} className="confirm-dialog motion-dialog fixed left-1/2 top-1/2 z-50 grid w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 gap-4 rounded-xl border border-line bg-surface p-6 shadow-panel">
        <Dialog.Title className="font-display text-title font-semibold text-ink">{content.title}</Dialog.Title>
        {content.children}
        <Dialog.Description className="text-body text-ink-secondary">{content.description}</Dialog.Description>
        {error ? <div role="alert" className="text-body text-danger-text">{error}</div> : null}
        <div className="flex justify-end gap-3">
          <button type="button" className={ghostButtonClass} disabled={busy} onClick={onClose}>{cancelLabel}</button>
          <button type="button" className={destructive ? dangerButtonClass : primaryButtonClass} disabled={busy} onClick={onConfirm}>{busy ? busyLabel : confirmLabel}</button>
        </div>
      </Dialog.Popup>
    </Dialog.Portal>
  </Dialog.Root>;
}
