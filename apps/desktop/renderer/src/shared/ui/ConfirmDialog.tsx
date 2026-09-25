import { useState, type ReactNode } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { InlineError } from "../feedback/InlineError";
import { MascotFaceAvatar } from "../mascot/MascotFigure";
import { MascotOnStage, useMascotCameoAllowed } from "../mascot/MascotOnStage";
import { MascotSpeechBubble } from "../mascot/MascotSpeech";
import type { MascotLine } from "../mascot/mascotLines";
import { dangerButtonClass, ghostButtonClass, primaryButtonClass } from "../styles";

/** Props of `ConfirmDialog` (plugins get it as `PluginHostServices.ui.ConfirmDialog`, with a plugin persona instead). */
export type ConfirmDialogProps = {
  open: boolean; title: string; description: string; confirmLabel: string; children?: ReactNode;
  busy?: boolean; busyLabel?: string; cancelLabel?: string; error?: string; destructive?: boolean; onClose: () => void; onConfirm: () => void;
  /** 吟风's lead line for this confirmation (see `confirmPersonaLines`). */
  persona?: MascotLine;
  /** Optional stable focus destination when a successful action removes its trigger. */
  finalFocus?: Dialog.Popup.Props["finalFocus"];
};

/**
 * Accessible confirmation shell with a non-dismissable in-flight action.
 *
 * `persona` lets 吟风 lead the dialog (host call sites pass one of
 * `confirmPersonaLines`): with the 看板娘 on, her face and that line sit
 * under the title, before the factual consequence text, which stays as it
 * is. Without `persona`, or with the 看板娘 off, the dialog is plain —
 * plugin dialogs never get her unless they ask.
 */
export function ConfirmDialog({ open, title, description, confirmLabel, children, busy = false, busyLabel = "删除中...", cancelLabel = "取消", error = "", destructive = true, persona, finalFocus, onClose, onConfirm }: ConfirmDialogProps) {
  // Callers usually derive the copy from the pending item and clear it on
  // close; keep showing the last open copy so the exit animation does not
  // play on an emptied, resized dialog.
  const [shown, setShown] = useState({ title, description, children, persona });
  if (open && (shown.title !== title || shown.description !== description || shown.children !== children || shown.persona !== persona)) {
    setShown({ title, description, children, persona });
  }
  const content = open ? { title, description, children, persona } : shown;
  const lead = useMascotCameoAllowed() ? content.persona : undefined;
  return <Dialog.Root open={open} onOpenChange={(next) => { if (!next && !busy) onClose(); }}>
    <Dialog.Portal>
      <Dialog.Backdrop className="confirm-dialog-backdrop motion-backdrop fixed inset-0 z-50 bg-ink/30 backdrop-blur-sm" />
      <Dialog.Popup finalFocus={finalFocus} className="confirm-dialog motion-dialog fixed left-1/2 top-1/2 z-50 grid w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 gap-4 rounded-xl border border-line bg-surface p-6 shadow-panel">
        <Dialog.Title className="font-display text-title font-semibold text-ink">{content.title}</Dialog.Title>
        {lead ? (
          // Her line is the dialog's lead sentence; the facts follow below.
          <div className="flex items-start gap-3" data-testid="confirm-persona" data-expression={lead.expression}>
            <MascotFaceAvatar expression={lead.expression} size="lg" />
            <MascotSpeechBubble line={lead} tail="left" className="min-w-0 flex-1" />
          </div>
        ) : null}
        {/* She already fronts this dialog: an error inside it stays plain. */}
        <MascotOnStage active={Boolean(lead)}>
          {content.children}
          <Dialog.Description className="text-body text-ink-secondary">{content.description}</Dialog.Description>
          {error ? <InlineError message={error} persona={false} /> : null}
        </MascotOnStage>
        <div className="flex justify-end gap-3">
          <button type="button" className={ghostButtonClass} disabled={busy} onClick={onClose}>{cancelLabel}</button>
          <button type="button" className={destructive ? dangerButtonClass : primaryButtonClass} disabled={busy} onClick={onConfirm}>{busy ? busyLabel : confirmLabel}</button>
        </div>
      </Dialog.Popup>
    </Dialog.Portal>
  </Dialog.Root>;
}
