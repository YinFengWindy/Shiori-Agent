import { sceneBackgroundSrc } from "../content/siteAssets";

/**
 * Full-viewport scene background shared by every screen: the lavender
 * bedroom, cover-fitted and unblurred, under a very light veil that keeps
 * the brightest curtains from competing with the UI. Decorative only.
 */
export function SiteScene() {
  return (
    <div className="site-scene pointer-events-none absolute inset-0" aria-hidden="true">
      <img src={sceneBackgroundSrc} alt="" className="site-scene-image h-full w-full object-cover" />
      <div className="site-scene-veil absolute inset-0" />
    </div>
  );
}
