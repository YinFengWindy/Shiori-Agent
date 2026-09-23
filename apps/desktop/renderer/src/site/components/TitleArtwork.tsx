import { titleSprites } from "../content/siteAssets";
import { cx } from "../siteClassNames";

interface TitleArtworkProps {
  index: number;
  onAdvance: () => void;
}

/**
 * 吟风's cut-out standing sprite over the room background: one of the three
 * title sprites, anchored to the bottom (feet may be cropped) — on the right
 * on desktop, centred behind the menu on narrow screens (see
 * `.site-title-sprite-stage` in site.css). Clicking the sprite advances to
 * the next one (cross-fade, instant under reduced motion). The dot
 * indicators live in `TitleArtworkDots`, rendered alongside the menu.
 */
export function TitleArtwork({ index, onAdvance }: TitleArtworkProps) {
  return (
    <div className="site-sprite-layer absolute inset-0">
      <div className="site-sprite-stage site-title-sprite-stage absolute">
        {titleSprites.map((sprite, i) => (
          <img
            key={sprite.src}
            src={sprite.src}
            alt={i === index ? sprite.alt : ""}
            aria-hidden={i !== index}
            className={cx("site-sprite", i === index ? "site-sprite-active" : "site-sprite-inactive")}
          />
        ))}
        <button type="button" onClick={onAdvance} aria-label="切换下一张吟风立绘" className="site-sprite-advance absolute inset-0 h-full w-full" />
      </div>
    </div>
  );
}
