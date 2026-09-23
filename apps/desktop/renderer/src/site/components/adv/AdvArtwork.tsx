import { advArtwork } from "../../content/siteAssets";
import type { AdvArtKey } from "../../content/advScript";
import { cx } from "../../siteClassNames";

const ART_KEYS = Object.keys(advArtwork) as AdvArtKey[];

interface AdvArtworkProps {
  art: AdvArtKey;
}

/**
 * The ADV screen's standing art, in the same place and with the same
 * feathering as the title screen's (see `.site-artwork-*` in site.css).
 * Every slot is stacked and cross-faded, so switching topics fades rather
 * than popping; only the active image is exposed to assistive tech.
 */
export function AdvArtwork({ art }: AdvArtworkProps) {
  return (
    <div className="site-title-art-layer site-adv-art-layer absolute inset-0">
      <div className="site-artwork-viewport absolute">
        {ART_KEYS.map((key) => (
          <img
            key={key}
            src={advArtwork[key].src}
            alt={key === art ? advArtwork[key].alt : ""}
            aria-hidden={key !== art}
            className={cx("site-artwork-image absolute inset-0 h-full w-full", key === art ? "site-artwork-image-active" : "site-artwork-image-inactive")}
          />
        ))}
        <div className="site-artwork-scrim absolute inset-0" aria-hidden="true" />
      </div>
    </div>
  );
}
