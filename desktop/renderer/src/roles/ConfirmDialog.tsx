import { useEffect } from "react";
import { cx, focusResetClass } from "../shared/styles";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel?: string;
  busy?: boolean;
  onClose: () => void;
  onConfirm: () => void;
};

/** Renders a reusable confirmation dialog for destructive desktop actions. */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "取消",
  busy = false,
  onClose,
  onConfirm,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleEscape(event: KeyboardEvent): void {
      if (event.key !== "Escape" || busy) return;
      event.preventDefault();
      onClose();
    }

    window.addEventListener("keydown", handleEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleEscape);
    };
  }, [busy, onClose, open]);

  if (!open) return null;

  return (
    <div className="confirm-dialog fixed inset-0 z-40 flex items-center justify-center px-4 py-6">
      <button
        className="confirm-dialog-backdrop absolute inset-0 border-0 bg-[rgba(15,23,42,0.34)] p-0 backdrop-blur-[6px]"
        type="button"
        aria-label="关闭确认弹层"
        onClick={onClose}
        disabled={busy}
      />
      <section
        className="relative z-[1] w-full max-w-[460px] rounded-[24px] bg-[rgba(255,255,255,0.98)] p-6 shadow-[0_28px_80px_rgba(15,23,42,0.18)]"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="text-[20px] font-semibold text-[#202020]">{title}</div>
        <div className="mt-2 text-sm leading-6 text-[#5E5E5E]">{description}</div>
        <div className="mt-6 flex justify-end gap-3">
          <button
            className={cx(
              "rounded-md border border-[#D8DFE7] bg-white px-4 py-2.5 text-sm text-[#3B4652] transition",
              "hover:border-[#C7D1DB] hover:bg-[#F7F9FB]",
              focusResetClass,
              busy && "cursor-default opacity-60",
            )}
            type="button"
            onClick={onClose}
            disabled={busy}
          >
            {cancelLabel}
          </button>
          <button
            className={cx(
              "rounded-md border border-[rgba(143,43,24,0.22)] bg-[rgba(143,43,24,0.92)] px-4 py-2.5 text-sm text-white transition",
              "hover:bg-[rgba(143,43,24,1)]",
              focusResetClass,
              busy && "cursor-default opacity-60",
            )}
            type="button"
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "删除中..." : confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}
