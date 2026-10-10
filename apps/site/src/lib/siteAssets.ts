import type { ImageMetadata } from "astro";
import type { ScenePhase } from "../../../desktop/renderer/src/shared/scene/timeOfDay";
import sceneDay from "../../../desktop/renderer/src/shared/assets/scene/bg-day.webp";
import sceneDusk from "../../../desktop/renderer/src/shared/assets/scene/bg-dusk.webp";
import sceneNight from "../../../desktop/renderer/src/shared/assets/scene/bg-night.webp";
import titleLogo from "../../../desktop/renderer/public/assets/branding/shiori-title-logo.png";
import sprite1 from "../assets/art/sprite-1.webp";
import ogCover from "../assets/social/og-cover.jpg";

/** One site image: the build-time image metadata plus its accessible alt text. */
export interface SiteImage {
  readonly image: ImageMetadata;
  readonly alt: string;
}

/**
 * The pictures the pages show, grouped by role. Pages import art from here
 * rather than reaching into `../assets/`, so swapping a picture is a one-file
 * change; only what a page uses is imported, because every imported image is
 * emitted into the build. `tests/assets.test.ts` checks that each
 * `../assets/art/*.webp` import above exists, and owns the WebP
 * size/metadata hygiene of every file in that directory — including the art
 * kept there for the narrative and gallery that come next (#768). The BGM in
 * `../assets/audio/` is likewise kept for later and has no check yet.
 *
 * The scene backgrounds and the title logo are the desktop's own files
 * (first-run guide / startup splash, story plugin) and are imported from
 * there instead of being copied.
 */

/** Time-of-day scene backgrounds (decorative; phase boundaries in desktop `timeOfDay.ts`). */
export const sceneBackgrounds: Record<ScenePhase, ImageMetadata> = {
  day: sceneDay,
  dusk: sceneDusk,
  night: sceneNight,
};

/** 「栞 / SHIORI」 title logo. */
export const titleLogoImage: ImageMetadata = titleLogo;

/** 吟风's cut-out standing sprite (transparent WebP) in the hero, over the scene. */
export const heroSprite: SiteImage = {
  image: sprite1,
  alt: "吟风立绘：黑色哥特连衣裙配过膝袜，背后展开蝙蝠翼，以手掩唇浅笑",
};

/**
 * Default social preview (OG / Twitter card): the seaside CG (cg-6)
 * cover-cropped to the 1200×630 card size, as JPEG because some link
 * previewers do not render WebP.
 */
export const socialPreviewImage: SiteImage = {
  image: ogCover,
  alt: "CG：晚霞海边的全身立绘，黑色蝙蝠翼连衣裙",
};
