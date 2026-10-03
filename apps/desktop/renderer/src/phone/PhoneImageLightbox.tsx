import { Dialog } from "@base-ui/react/dialog";
import { XIcon } from "@phosphor-icons/react";
import { toFileUrl } from "../shared/format";
import { cx } from "@yinfengwindy/shiori-sdk";
import { compactIconButtonClass, dialogBackdropClass } from "../shared/styles";

/**
 * A phone picture enlarged over the whole window, view only. Esc, the close
 * button or a click outside the picture closes it; focus moves in while it
 * is open and back to the picture it came from after. `imagePath` stays set
 * while it closes, so the exit fade still shows the picture.
 */
export function PhoneImageLightbox({ imagePath, open, onClose }: {
  imagePath: string;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Backdrop className={dialogBackdropClass} />
        <Dialog.Popup aria-label="图片预览" data-testid="phone-image-lightbox"
          className="motion-dialog fixed left-1/2 top-1/2 z-50 -translate-x-1/2 -translate-y-1/2">
          {imagePath ? (
            <img className="block max-h-[calc(100dvh-4rem)] max-w-[calc(100vw-4rem)] rounded-md object-contain shadow-pop"
              src={toFileUrl(imagePath)} alt="" />
          ) : null}
          <Dialog.Close aria-label="关闭图片预览"
            className={cx(compactIconButtonClass, "surface-glass absolute right-2 top-2 text-ink")}>
            <XIcon className="h-4 w-4" aria-hidden="true" />
          </Dialog.Close>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
