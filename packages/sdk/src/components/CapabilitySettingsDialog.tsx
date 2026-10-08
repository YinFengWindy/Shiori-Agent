import type { ReactNode } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { GearSix, XIcon } from "@phosphor-icons/react";
import { compactIconButtonClass, dialogBackdropClass, iconButtonClass } from "../styles";

type CapabilitySettingsDialogProps = {
  /** The capability's name: the dialog title and the base of the ⚙ button's accessible name. */
  title: string;
  /** The capability's secondary settings, mounted only while the dialog is open. */
  children: ReactNode;
};

/**
 * The ⚙ button of a role capability card and the centred, medium-width dialog
 * it opens (runtime API 3.1.11, #719). Base UI owns the modal behaviour:
 * focus moves into the dialog and returns to the ⚙ on close, Escape and the
 * backdrop dismiss it. A long body scrolls inside the dialog while the title
 * row stays put. Edits inside follow whatever save rule the caller's fields
 * already have (the role draft, or a plugin's own autosave); the dialog never
 * saves or discards anything itself.
 */
export function CapabilitySettingsDialog({ title, children }: CapabilitySettingsDialogProps) {
  return (
    <Dialog.Root>
      <Dialog.Trigger className={compactIconButtonClass} aria-label={`${title}设置`}>
        <GearSix className="h-4 w-4" weight="bold" aria-hidden="true" />
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Backdrop className={dialogBackdropClass} />
        <Dialog.Popup className="motion-dialog fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-[min(40rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col gap-5 rounded-md border border-line bg-surface p-6 shadow-panel">
          <div className="flex shrink-0 items-start justify-between gap-4">
            <Dialog.Title className="m-0 min-w-0 break-words font-display text-title font-semibold text-ink">{title}</Dialog.Title>
            <Dialog.Close className={iconButtonClass} aria-label="关闭">
              <XIcon className="h-5 w-5" aria-hidden="true" />
            </Dialog.Close>
          </div>
          <div className="scrollbar-stable grid min-h-0 content-start gap-4 overflow-y-auto overscroll-contain" data-capability-settings-body="">
            {children}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
