import bgDay from "../assets/scene/bg-day.webp";
import bgDusk from "../assets/scene/bg-dusk.webp";
import bgNight from "../assets/scene/bg-night.webp";
import type { ScenePhase } from "./timeOfDay";

/**
 * Scene backgrounds shared by the public site (title, ADV, 人物, CG 鉴赏) and
 * the desktop first-run guide, one per time-of-day phase (see `timeOfDay.ts`):
 * a sakura street by day, a rooftop at dusk, an arched-window bedroom under
 * the moon at night. Purely decorative (rendered with an empty alt).
 *
 * Kept free of desktop business code so the site build can import it.
 */
export const sceneBackgrounds: Record<ScenePhase, string> = {
  day: bgDay,
  dusk: bgDusk,
  night: bgNight,
};
