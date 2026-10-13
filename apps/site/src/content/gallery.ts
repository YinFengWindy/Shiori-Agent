/**
 * The photo strip under the showcase (#772), in strip order: which piece of
 * `assets/art/` each print shows, and its alt text. The strip shows small
 * previews, not the art itself (#790): apps/site-video's gallery script
 * (`pnpm run site:gallery`) shrinks each `assets/art/<art>.webp` to
 * `GALLERY_THUMB_HEIGHT` pixels tall into `assets/gallery/<art>.webp`, which
 * `lib/siteAssets.ts` picks up by the same names.
 *
 * cg-1 (a bedroom scene, half-buttoned shirt) and cg-9 (bare shoulders under
 * a slipping jacket) are left out as too suggestive for a public strip.
 */
export const GALLERY_PHOTOS = [
  { art: "cg-3", alt: "CG：趴在粉色电脑桌前兴奋地打字" },
  { art: "cg-6", alt: "CG：晚霞海边的全身立绘，黑色蝙蝠翼连衣裙" },
  { art: "cg-7", alt: "CG：夜晚街头挽臂同行的温馨场景" },
  { art: "cg-5", alt: "CG：阳光洒落的窗边侧脸特写" },
  { art: "cg-8", alt: "CG：夜色中坐在公园长椅上，以手托腮微笑，发间系着蝙蝠翼造型的发绳" },
  { art: "cg-4", alt: "CG：窝在沙发上吃甜点的夜晚场景" },
  { art: "cg-10", alt: "CG：从门后探身张望，身后是温暖的暖色房间" },
  { art: "cg-2", alt: "CG：侧躺在床上，蓝紫色柔光近景" },
] as const satisfies readonly { readonly art: string; readonly alt: string }[];

/** A piece of art shown in the photo strip. */
export type GalleryArt = (typeof GALLERY_PHOTOS)[number]["art"];

/**
 * Height of every preview, in pixels: twice the strip's tallest print
 * (`--site-photo-height`, at most 15rem), so it is sharp on 2× screens.
 */
export const GALLERY_THUMB_HEIGHT = 480;

/** Size budget of every preview: the gallery script and the build test check it. */
export const GALLERY_THUMB_MAX_BYTES = 80 * 1024;
