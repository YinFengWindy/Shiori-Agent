import { cx } from "../siteClassNames";
import { titleArtwork } from "../content/siteAssets";
import { useTitleArtSelection } from "../titleArt/useTitleArtSelection";

/**
 * Right-side standing art: one of the three title images, chosen at random
 * per visit. Clicking the art advances to the next image (fade + slight
 * shift, instant under reduced motion); the dot indicators show and select
 * the current image directly.
 */
export function TitleArtwork() {
  const { index, advance, select } = useTitleArtSelection(titleArtwork.length);

  return (
    <div className="site-title-artwork relative flex flex-col items-center gap-4">
      <div className="site-artwork-frame relative overflow-hidden rounded-lg">
        {titleArtwork.map((art, i) => (
          <img
            key={art.src}
            src={art.src}
            alt={i === index ? art.alt : ""}
            aria-hidden={i !== index}
            className={cx("site-artwork-image absolute inset-0 h-full w-full object-cover", i === index ? "site-artwork-image-active" : "site-artwork-image-inactive")}
          />
        ))}
        <button
          type="button"
          onClick={advance}
          aria-label="切换下一张吟风立绘"
          className="site-artwork-advance absolute inset-0 h-full w-full"
        />
      </div>
      <div role="group" aria-label="立绘选择" className="flex items-center gap-2">
        {titleArtwork.map((art, i) => (
          <button
            key={art.src}
            type="button"
            onClick={() => select(i)}
            aria-label={`查看第 ${i + 1} 张立绘`}
            aria-pressed={i === index}
            className={cx("site-artwork-dot h-2.5 w-2.5 rounded-full", i === index && "site-artwork-dot-active")}
          />
        ))}
      </div>
    </div>
  );
}
