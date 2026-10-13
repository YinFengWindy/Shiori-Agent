import type { ImageMetadata } from "astro";
import type { MascotExpression } from "../../../desktop/renderer/src/shared/mascot/mascotExpressions";
import type { ScenePhase } from "../../../desktop/renderer/src/shared/scene/timeOfDay";
import mascotConfused from "../../../desktop/renderer/src/shared/assets/mascot/yinfeng-confused.webp";
import mascotLaugh from "../../../desktop/renderer/src/shared/assets/mascot/yinfeng-laugh.webp";
import mascotNeutral from "../../../desktop/renderer/src/shared/assets/mascot/yinfeng-neutral.webp";
import mascotPout from "../../../desktop/renderer/src/shared/assets/mascot/yinfeng-pout.webp";
import mascotSad from "../../../desktop/renderer/src/shared/assets/mascot/yinfeng-sad.webp";
import mascotShy from "../../../desktop/renderer/src/shared/assets/mascot/yinfeng-shy.webp";
import mascotSmug from "../../../desktop/renderer/src/shared/assets/mascot/yinfeng-smug.webp";
import mascotSurprised from "../../../desktop/renderer/src/shared/assets/mascot/yinfeng-surprised.webp";
import sceneDay from "../../../desktop/renderer/src/shared/assets/scene/bg-day.webp";
import sceneDusk from "../../../desktop/renderer/src/shared/assets/scene/bg-dusk.webp";
import sceneNight from "../../../desktop/renderer/src/shared/assets/scene/bg-night.webp";
import cg3 from "../assets/art/cg-3.webp";
import cg6 from "../assets/art/cg-6.webp";
import cg7 from "../assets/art/cg-7.webp";
import cg8 from "../assets/art/cg-8.webp";
import cg9 from "../assets/art/cg-9.webp";
import cg10 from "../assets/art/cg-10.webp";
import topic1 from "../assets/art/topic-1.webp";
import topic2 from "../assets/art/topic-2.webp";
import topic3 from "../assets/art/topic-3.webp";
import ogCover from "../assets/social/og-cover.jpg";
import { GALLERY_PHOTOS } from "../content/gallery";
import type { NarrativeCgKey } from "../content/narrative";
import type { ShowcaseClipId } from "../content/showcase";

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
 * size/metadata hygiene of every file in that directory — including art
 * no page shows (yet), kept for later use.
 *
 * The scene backgrounds and 吟风's expression sprites are the desktop's
 * own files (first-run guide / startup splash, the app's mascot) and are
 * imported from there instead of being copied.
 */

/** Time-of-day scene backgrounds (decorative; phase boundaries in desktop `timeOfDay.ts`). */
export const sceneBackgrounds: Record<ScenePhase, ImageMetadata> = {
  day: sceneDay,
  dusk: sceneDusk,
  night: sceneNight,
};

/**
 * The app icon (吟风's portrait) heading the download state: the 512px PNG
 * the site already serves as its manifest icon (public/icons), sharp at the
 * ≤ 176 CSS px it is shown at on 2× screens and 91 KB, where the 1024px
 * repository original is 1.6 MB and the site has no image optimiser.
 */
export const appIconImage = { src: "/icons/icon-512.png", width: 512, height: 512 } as const;

/**
 * The app icon in the top bar (#773), shown at 32 CSS px: the 192px
 * manifest icon (19 KB) is sharp there on 3× screens, a fifth of the 512px
 * file's weight.
 */
export const barIconImage = { src: "/icons/icon-192.png", width: 192, height: 192 } as const;

/**
 * 吟风's uniform standing sprite in the narrative, one image per expression
 * (the desktop mascot's set: 826×1213, one shared alpha mask, so a
 * cross-fade only changes the face). Decorative: her lines are real text.
 */
export const narrativeExpressionSprites: Record<MascotExpression, ImageMetadata> = {
  neutral: mascotNeutral,
  smug: mascotSmug,
  laugh: mascotLaugh,
  shy: mascotShy,
  confused: mascotConfused,
  pout: mascotPout,
  sad: mascotSad,
  surprised: mascotSurprised,
};

const mascotFileBytes = import.meta.glob<number>("../../../desktop/renderer/src/shared/assets/mascot/yinfeng-*.webp", {
  query: "?bytes",
  import: "default",
  eager: true,
});
const sceneFileBytes = import.meta.glob<number>("../../../desktop/renderer/src/shared/assets/scene/bg-*.webp", {
  query: "?bytes",
  import: "default",
  eager: true,
});

/** The entry of an `import.meta.glob` result whose file is named `name`. */
function globFile<T>(files: Record<string, T>, name: string): T {
  const entry = Object.entries(files).find(([path]) => path.endsWith(`/${name}`));
  if (!entry) throw new Error(`no file named ${name}`);
  return entry[1];
}

/**
 * Size in bytes of every picture the narrative's first screen may wait for
 * (each time-of-day scene, each expression sprite), by emitted URL: the home
 * page loader weighs its progress bar by these.
 */
export const firstScreenImageBytes: Readonly<Record<string, number>> = Object.fromEntries([
  ...Object.entries(sceneBackgrounds).map(([phase, image]) => [image.src, globFile(sceneFileBytes, `bg-${phase}.webp`)]),
  ...Object.entries(narrativeExpressionSprites).map(([expression, image]) => [
    image.src,
    globFile(mascotFileBytes, `yinfeng-${expression}.webp`),
  ]),
]);

/** Event CGs framed beside 吟风 while a narrative line plays (keys named by `content/narrative.ts`). */
export const narrativeCgs: Record<NarrativeCgKey, SiteImage> = {
  "cg-3": { image: cg3, alt: "CG：趴在粉色电脑桌前兴奋地打字" },
  "cg-7": { image: cg7, alt: "CG：夜晚街头挽臂同行的温馨场景" },
  "cg-8": { image: cg8, alt: "CG：夜色中坐在公园长椅上，以手托腮微笑，发间系着蝙蝠翼造型的发绳" },
  "cg-9": { image: cg9, alt: "CG：倚在夜景窗边，外套披在肩头，回望镜头" },
  "cg-10": { image: cg10, alt: "CG：从门后探身张望，身后是温暖的暖色房间" },
  "topic-1": { image: topic1, alt: "吟风配图：倚在洒满阳光的窗边，居家休闲装扮" },
  "topic-2": { image: topic2, alt: "吟风配图：坐在课桌前看手机，逆光的教室场景" },
  "topic-3": { image: topic3, alt: "吟风配图：月夜窗边浅笑，黑色晚装缀有蝙蝠翼装饰" },
};

/**
 * The home page loader's backdrop (#770): 吟风 with her wings spread, full
 * length on a pale seaside (1920×1088, about 108 KB), framed by `cover`.
 * Decorative: the loader is hidden from assistive technology.
 */
export const loaderArtwork: ImageMetadata = cg6;

/**
 * Default social preview (OG / Twitter card): the seaside CG (cg-6)
 * cover-cropped to the 1200×630 card size, as JPEG because some link
 * previewers do not render WebP.
 */
export const socialPreviewImage: SiteImage = {
  image: ogCover,
  alt: "CG：晚霞海边的全身立绘，黑色蝙蝠翼连衣裙",
};

/**
 * The showcase stills (#790), by clip id (`SHOWCASE_CLIP_IDS` in
 * `content/showcase.ts`): one frame of each demo clip, rendered by
 * apps/site-video (`pnpm run site:stills`) and committed; the site build only
 * copies them. The page shows these instead of the clips themselves, which
 * stalled on slow or flaky lines.
 */
const showcaseStills = import.meta.glob<ImageMetadata>("../assets/showcase/*.webp", { import: "default", eager: true });

/** A showcase still, by its clip id. */
export function showcaseStill(id: ShowcaseClipId): ImageMetadata {
  return globFile(showcaseStills, `${id}.webp`);
}

const galleryThumbs = import.meta.glob<ImageMetadata>("../assets/gallery/*.webp", { import: "default", eager: true });

/**
 * The photo strip under the showcase, in strip order (`content/gallery.ts`):
 * each print is a small preview of its art, made by apps/site-video
 * (`pnpm run site:gallery`) and committed, not the full-size file.
 */
export const galleryPhotos: readonly SiteImage[] = GALLERY_PHOTOS.map(({ art, alt }) => ({
  image: globFile(galleryThumbs, `${art}.webp`),
  alt,
}));

/*
 * The full-size art of the photo strip's previews, by name: the arts named in
 * GALLERY_PHOTOS (content/gallery.ts), spelled out because a glob pattern must
 * be literal. Not every file in assets/art: each file a glob names is emitted
 * into the build, and some of the art (cg-1) is deliberately kept off the
 * public site. A preview missing here fails `galleryArtOf` with its name.
 */
const fullArt = import.meta.glob<ImageMetadata>("../assets/art/{cg-2,cg-3,cg-4,cg-5,cg-6,cg-7,cg-8,cg-10}.webp", {
  import: "default",
  eager: true,
});

/**
 * The full-size art a photo strip preview was shrunk from (same file name in
 * `assets/art/`), for a picture larger than the preview (a post's share
 * picture, #799); `undefined` when `image` is not one of the previews.
 */
export function galleryArtOf(image: ImageMetadata): ImageMetadata | undefined {
  const preview = Object.keys(galleryThumbs).find((path) => galleryThumbs[path]?.src === image.src);
  if (preview === undefined) return undefined;
  return globFile(fullArt, preview.slice(preview.lastIndexOf("/") + 1));
}
