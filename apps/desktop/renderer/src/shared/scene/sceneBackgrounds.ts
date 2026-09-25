import type { ScenePhase } from "./timeOfDay";

/**
 * Scene backgrounds shared by the public site (title, ADV, 人物, CG 鉴赏) and
 * the desktop first-run guide and startup splash, one per time-of-day phase
 * (see `timeOfDay.ts`): a sakura street by day, a rooftop at dusk, an
 * arched-window bedroom under the moon at night. Purely decorative (rendered
 * with an empty alt).
 *
 * Resolved with `new URL(…, import.meta.url)` so the plain Node test runner
 * can load components that show them (Vite emits them as usual). Kept free
 * of desktop business code so the site build can import it.
 */
export const sceneBackgrounds: Record<ScenePhase, string> = {
  day: new URL("../assets/scene/bg-day.webp", import.meta.url).href,
  dusk: new URL("../assets/scene/bg-dusk.webp", import.meta.url).href,
  night: new URL("../assets/scene/bg-night.webp", import.meta.url).href,
};
