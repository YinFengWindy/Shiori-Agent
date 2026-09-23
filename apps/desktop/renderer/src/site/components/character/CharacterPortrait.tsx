import type { CharacterOutfit } from "../../content/characterProfile";
import { cx } from "../../siteClassNames";

interface CharacterPortraitProps {
  outfits: readonly CharacterOutfit[];
  index: number;
}

/**
 * 吟风's standing art for the selected outfit, framed like a picture card on
 * the scene. All outfits are stacked so a switch cross-fades (instant under
 * reduced motion); only the shown one is exposed with its alt text.
 */
export function CharacterPortrait({ outfits, index }: CharacterPortraitProps) {
  return (
    <div className="site-character-portrait relative overflow-hidden rounded-xl">
      {outfits.map((outfit, i) => (
        <img
          key={outfit.art.src}
          src={outfit.art.src}
          alt={i === index ? outfit.art.alt : ""}
          aria-hidden={i !== index}
          className={cx("site-character-art absolute inset-0 h-full w-full object-cover", i === index ? "site-character-art-active" : "site-character-art-inactive")}
        />
      ))}
    </div>
  );
}
