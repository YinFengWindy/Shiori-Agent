import { useState, type ReactNode } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { GearSix } from "@phosphor-icons/react";
import { compactIconButtonClass } from "../styles";
import { DialogFrame } from "./DialogFrame";

type CapabilitySettingsDialogProps = {
  /** The capability's name: the dialog title and the base of the ⚙ button's accessible name. */
  title: string;
  /** The capability's secondary settings; mounted on first open, then kept (see `RoleCapabilityCard.settings`). */
  children: ReactNode;
  /** Called with each open and close (runtime API 3.1.12), e.g. to commit a pending autosave on close. */
  onOpenChange?: (open: boolean) => void;
};

/**
 * The ⚙ button of a role capability card and the centred, medium-width dialog
 * it opens (runtime API 3.1.11, #719). Base UI owns the modal behaviour:
 * focus moves into the dialog and returns to the ⚙ on close, Escape and the
 * backdrop dismiss it. A long body scrolls inside the dialog while the title
 * row stays put. The dialog never saves or discards anything itself.
 */
export function CapabilitySettingsDialog({ title, children, onOpenChange }: CapabilitySettingsDialogProps) {
  // Nothing mounts until the first open; after that the content stays mounted
  // (hidden while closed) so its pending autosave or failed-save retry survives a close.
  const [opened, setOpened] = useState(false);
  return (
    <Dialog.Root onOpenChange={(open) => { if (open) setOpened(true); onOpenChange?.(open); }}>
      <Dialog.Trigger className={compactIconButtonClass} aria-label={`${title}设置`}>
        <GearSix className="h-4 w-4" weight="bold" aria-hidden="true" />
      </Dialog.Trigger>
      <DialogFrame title={title} closeLabel="关闭" keepMounted={opened} bodyClassName="grid content-start gap-4">
        {children}
      </DialogFrame>
    </Dialog.Root>
  );
}
