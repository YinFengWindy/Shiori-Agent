import { titleArtwork } from "../content/siteAssets";
import { cx } from "../siteClassNames";

interface TitleArtworkProps {
  index: number;
  onAdvance: () => void;
}

/**
 * Full-bleed standing art layer: one of the three title images. On desktop
 * it's anchored bottom-right, spans nearly the full viewport height and
 * bleeds off the bottom/right edge; on narrow screens it covers the whole
 * title screen behind the menu. Clicking the art advances to the next image
 * (fade + slight shift, instant under reduced motion). No card frame/border
 * — `site.css` feathers the art into the night background with a mask (left
 * edge on desktop) and a gradient scrim (bottom, and a touch of top) instead
 * of a hard rectangle. The dot indicators live in `TitleArtworkDots`,
 * rendered alongside the menu so their position doesn't have to be guessed
 * against the art's responsive sizing.
 */
export function TitleArtwork({ index, onAdvance }: TitleArtworkProps) {
  return (
    <div className="site-title-art-layer absolute inset-0">
      <div className="site-artwork-viewport absolute">
        {titleArtwork.map((art, i) => (
          <img
            key={art.src}
            src={art.src}
            alt={i === index ? art.alt : ""}
            aria-hidden={i !== index}
            className={cx("site-artwork-image absolute inset-0 h-full w-full", i === index ? "site-artwork-image-active" : "site-artwork-image-inactive")}
          />
        ))}
        <div className="site-artwork-scrim absolute inset-0" aria-hidden="true" />
        <button
          type="button"
          onClick={onAdvance}
          aria-label="切换下一张吟风立绘"
          className="site-artwork-advance absolute inset-0 h-full w-full"
        />
      </div>
    </div>
  );
}
