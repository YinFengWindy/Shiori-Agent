import { useEffect, type RefObject } from "react";

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Modal dialog focus management: focus `initialFocus` (or the first
 * focusable element) on open, keep Tab / Shift+Tab cycling inside the
 * dialog, and hand focus back to whatever had it before on close.
 */
export function useDialogFocus(dialogRef: RefObject<HTMLElement | null>, initialFocus?: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    (initialFocus?.current ?? dialog.querySelector<HTMLElement>(FOCUSABLE))?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Tab" || !dialog) return;
      const items = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    dialog.addEventListener("keydown", handleKeyDown);
    return () => {
      dialog.removeEventListener("keydown", handleKeyDown);
      previous?.focus();
    };
  }, [dialogRef, initialFocus]);
}
