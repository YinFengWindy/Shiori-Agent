/**
 * The photo strip under the showcase (#772), in strip order: which piece of
 * `assets/art/` each print shows; its alt text is the dictionaries'
 * `art[<art>]` (i18n/zh.ts, i18n/en.ts). The strip shows small
 * previews, not the art itself (#790): apps/site-video's gallery script
 * (`pnpm run site:gallery`) shrinks each `assets/art/<art>.webp` to
 * `GALLERY_THUMB_HEIGHT` pixels tall into `assets/gallery/<art>.webp`, which
 * `lib/siteAssets.ts` picks up by the same names.
 *
 * cg-1 (a bedroom scene, half-buttoned shirt) and cg-9 (bare shoulders under
 * a slipping jacket) are left out as too suggestive for a public strip.
 */
export const GALLERY_ARTS = ["cg-3", "cg-6", "cg-7", "cg-5", "cg-8", "cg-4", "cg-10", "cg-2"] as const;

/** A piece of art shown in the photo strip. */
export type GalleryArt = (typeof GALLERY_ARTS)[number];

/**
 * Height of every preview, in pixels: twice the strip's tallest print
 * (`--site-photo-height`, at most 15rem), so it is sharp on 2× screens.
 */
export const GALLERY_THUMB_HEIGHT = 480;

/** Size budget of every preview: the gallery script and the build test check it. */
export const GALLERY_THUMB_MAX_BYTES = 80 * 1024;
