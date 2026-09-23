import { SITE_GALLERY_COPY } from "../../content/siteCopy";
import type { SiteImage } from "../../content/siteAssets";
import { useButtonSfx } from "../../sound/useSound";

interface CgGridProps {
  images: readonly SiteImage[];
  onOpen: (index: number) => void;
  /** Registers each tile so focus can return to it when the lightbox closes. */
  thumbRef: (index: number) => (element: HTMLButtonElement | null) => void;
}

/**
 * CG thumbnails as uniform tiles (landscape and portrait art alike are
 * cover-cropped), each a button named after its image's alt text. The list
 * scrolls internally when it outgrows the screen (narrow phones).
 */
export function CgGrid({ images, onOpen, thumbRef }: CgGridProps) {
  const { hover } = useButtonSfx();
  return (
    <ul aria-label={SITE_GALLERY_COPY.gridLabel} className="site-gallery-grid grid min-h-0 overflow-y-auto">
      {images.map((image, i) => (
        <li key={image.src} className="min-w-0">
          <button
            ref={thumbRef(i)}
            type="button"
            onPointerEnter={hover}
            onClick={() => onOpen(i)}
            aria-label={SITE_GALLERY_COPY.open(i + 1, image.alt)}
            className="site-gallery-tile group relative block w-full overflow-hidden rounded-lg"
          >
            <img src={image.src} alt="" loading="lazy" className="site-gallery-tile-image h-full w-full object-cover" />
            <span className="site-gallery-tile-number font-display" aria-hidden="true">
              {SITE_GALLERY_COPY.tileNumber(i + 1)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
