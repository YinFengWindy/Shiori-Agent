import { SiteScene } from "../components/SiteScene";
import { SubScreenHeader } from "../components/SubScreenHeader";
import { CgGrid } from "../components/gallery/CgGrid";
import { CgLightbox } from "../components/gallery/CgLightbox";
import { galleryArtwork } from "../content/siteAssets";
import { SITE_GALLERY_COPY } from "../content/siteCopy";
import { useCgLightbox } from "../gallery/useCgLightbox";

interface GalleryScreenProps {
  onBack: () => void;
}

/**
 * 「CG 鉴赏」: every CG as a thumbnail tile on a glass panel over the room
 * scene; a tile opens the lightbox. Wiring only — the lightbox state is
 * `gallery/lightboxModel.ts`, driven (with sound and focus return) by
 * `useCgLightbox`.
 */
export function GalleryScreen({ onBack }: GalleryScreenProps) {
  const lightbox = useCgLightbox(galleryArtwork.length);
  const total = galleryArtwork.length;

  // The lightbox renders beside (not inside) the isolated screen so it
  // stacks above the global sound toggle, like the settings modal.
  return (
    <>
      <div className="site-screen site-subscreen relative flex h-dvh min-h-0 flex-col overflow-hidden">
        <SiteScene />
        <div className="site-subscreen-veil pointer-events-none absolute inset-0" aria-hidden="true" />
        <SubScreenHeader title={SITE_GALLERY_COPY.title} eyebrow={SITE_GALLERY_COPY.eyebrow} onBack={onBack}>
          <p className="site-gallery-count shrink-0 rounded-full">
            <span className="sr-only sm:not-sr-only">{SITE_GALLERY_COPY.collected} </span>
            <span className="site-gallery-count-value font-display">{`${total} / ${total}`}</span>
          </p>
        </SubScreenHeader>
        <main className="site-gallery-panel relative flex min-h-0 flex-col">
          <CgGrid images={galleryArtwork} onOpen={lightbox.openAt} thumbRef={lightbox.thumbRef} />
        </main>
      </div>
      {lightbox.open ? (
        <CgLightbox
          image={galleryArtwork[lightbox.index]}
          counter={lightbox.counter}
          onPrevious={lightbox.showPrevious}
          onNext={lightbox.showNext}
          onClose={lightbox.close}
        />
      ) : null}
    </>
  );
}
