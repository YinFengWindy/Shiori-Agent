import type { CharacterOutfit } from "../../content/characterProfile";
import { SITE_CHARACTER_COPY } from "../../content/siteCopy";
import { cx } from "../../siteClassNames";
import { useButtonSfx } from "../../sound/useSound";

interface CharacterOutfitPickerProps {
  outfits: readonly CharacterOutfit[];
  index: number;
  onSelect: (index: number) => void;
}

/**
 * 换装 thumbnails: one button per outfit (a face crop of its art plus the
 * outfit name), named by that label and marked with `aria-pressed`.
 * Laid out in a row on desktop and a column beside the art on mobile.
 */
export function CharacterOutfitPicker({ outfits, index, onSelect }: CharacterOutfitPickerProps) {
  const { hover, click } = useButtonSfx();
  return (
    <div role="group" aria-label={SITE_CHARACTER_COPY.outfits} className="site-character-outfits flex">
      {outfits.map((outfit, i) => (
        <button
          key={outfit.art.src}
          type="button"
          aria-pressed={i === index}
          onPointerEnter={hover}
          onClick={() => {
            if (i !== index) click();
            onSelect(i);
          }}
          className={cx("site-character-outfit flex flex-col items-center rounded-lg", i === index && "site-character-outfit-active")}
        >
          <span className="site-character-outfit-thumb block overflow-hidden rounded-md" aria-hidden="true">
            <img src={outfit.art.src} alt="" className="h-full w-full object-cover" />
          </span>
          <span className="site-character-outfit-label font-display">{outfit.label}</span>
        </button>
      ))}
    </div>
  );
}
