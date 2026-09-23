import { sceneBackgrounds } from "../content/siteAssets";
import { pageLoadScenePhase } from "../scene/pageLoadScenePhase";

/**
 * Full-viewport scene background shared by every screen: the current
 * time-of-day phase's picture (chosen once at page load), cover-fitted and
 * unblurred, under a very light veil. The glass UI reads on all three
 * phases as-is, so there is no per-phase tuning. Decorative only.
 */
export function SiteScene() {
  return (
    <div className="site-scene pointer-events-none absolute inset-0" aria-hidden="true">
      <img src={sceneBackgrounds[pageLoadScenePhase]} alt="" className="site-scene-image h-full w-full object-cover" />
      <div className="site-scene-veil absolute inset-0" />
    </div>
  );
}
