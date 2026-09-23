import { useRef, type KeyboardEvent, type MouseEvent } from "react";
import { CaretLeft, CaretRight, X } from "@phosphor-icons/react";
import type { SiteImage } from "../../content/siteAssets";
import { SITE_GALLERY_COPY } from "../../content/siteCopy";
import { useDialogFocus } from "../../hooks/useDialogFocus";
import { useButtonSfx } from "../../sound/useSound";

interface CgLightboxProps {
  image: SiteImage;
  counter: string;
  onPrevious: () => void;
  onNext: () => void;
  onClose: () => void;
}

// Clicks on the picture and the controls must not reach the backdrop.
function stop(event: MouseEvent) {
  event.stopPropagation();
}

/** Click handler that runs `action` without also triggering the backdrop close. */
function isolated(action: () => void) {
  return (event: MouseEvent) => {
    event.stopPropagation();
    action();
  };
}

/**
 * Full-screen CG viewer: the image contained in the viewport, 上一张/下一张
 * buttons and ←/→ (wrap-around), a "3 / 10" counter with the alt text as a
 * caption. Esc, right-click, the close button or a click on the backdrop
 * close the lightbox only — Esc/right-click are stopped here so
 * `useSiteScreen` doesn't also leave the gallery, like the ADV backlog.
 */
export function CgLightbox({ image, counter, onPrevious, onNext, onClose }: CgLightboxProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useDialogFocus(dialogRef, closeRef);
  const { hover } = useButtonSfx();

  function handleKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      onPrevious();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      onNext();
    }
  }

  function handleContextMenu(event: MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    onClose();
  }

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label={SITE_GALLERY_COPY.lightboxLabel}
      tabIndex={-1}
      onKeyDown={handleKeyDown}
      onClick={onClose}
      onContextMenu={handleContextMenu}
      className="site-lightbox site-modal-backdrop fixed inset-0 z-50 grid"
    >
      <button ref={closeRef} type="button" onClick={isolated(onClose)} onPointerEnter={hover} aria-label={SITE_GALLERY_COPY.close} className="site-lightbox-close site-lightbox-button rounded-full">
        <X size={20} aria-hidden="true" />
      </button>
      <figure className="site-lightbox-figure flex min-h-0 min-w-0 flex-col items-center justify-center">
        <img key={image.src} src={image.src} alt={image.alt} onClick={stop} className="site-lightbox-image rounded-xl" />
        <figcaption onClick={stop} className="site-lightbox-caption flex max-w-full items-baseline gap-3">
          <span className="site-lightbox-counter shrink-0 font-display" aria-live="polite">
            {counter}
          </span>
          <span className="site-lightbox-alt min-w-0 truncate" aria-hidden="true">{image.alt}</span>
        </figcaption>
      </figure>
      <button type="button" onClick={isolated(onPrevious)} onPointerEnter={hover} aria-label={SITE_GALLERY_COPY.previous} className="site-lightbox-prev site-lightbox-button rounded-full">
        <CaretLeft size={22} aria-hidden="true" />
      </button>
      <button type="button" onClick={isolated(onNext)} onPointerEnter={hover} aria-label={SITE_GALLERY_COPY.next} className="site-lightbox-next site-lightbox-button rounded-full">
        <CaretRight size={22} aria-hidden="true" />
      </button>
    </div>
  );
}
