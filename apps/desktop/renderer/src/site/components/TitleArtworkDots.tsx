import { titleArtwork } from "../content/siteAssets";
import { cx } from "../siteClassNames";

interface TitleArtworkDotsProps {
  index: number;
  onSelect: (index: number) => void;
}

/** Dot indicators for the title art, rendered next to the menu (see TitleScreen). */
export function TitleArtworkDots({ index, onSelect }: TitleArtworkDotsProps) {
  return (
    <div role="group" aria-label="立绘选择" className="site-artwork-dots flex items-center gap-2">
      {titleArtwork.map((art, i) => (
        <button
          key={art.src}
          type="button"
          onClick={() => onSelect(i)}
          aria-label={`查看第 ${i + 1} 张立绘`}
          aria-pressed={i === index}
          className={cx("site-artwork-dot h-2.5 w-2.5 rounded-full", i === index && "site-artwork-dot-active")}
        />
      ))}
    </div>
  );
}
