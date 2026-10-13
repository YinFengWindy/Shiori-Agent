/**
 * Shrinks the website photo strip's art (#790): every `GALLERY_ARTS` entry
 * of apps/site/src/content/gallery.ts, from `apps/site/src/assets/art/<art>.webp`
 * to `GALLERY_THUMB_HEIGHT` pixels tall in `apps/site/src/assets/gallery/<art>.webp`.
 * The site build only reads those committed files; run this
 * (`pnpm run site:gallery`) after changing the strip's list or its art, and
 * commit the output. Files no entry names any more are deleted.
 *
 * It lives here, beside the clips' render scripts, because this package
 * already carries the image tooling (sharp); the site's own build stays free
 * of it.
 *
 * Usage: `tsx scripts/gallery.ts`.
 */
import { mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import sharp from "sharp";
import { GALLERY_ARTS, GALLERY_THUMB_HEIGHT, GALLERY_THUMB_MAX_BYTES } from "../../site/src/content/gallery";

const here = dirname(fileURLToPath(import.meta.url));
const artDir = resolve(here, "../../site/src/assets/art");
const outDir = resolve(here, "../../site/src/assets/gallery");

/** WebP quality: soft enough for the budget, still clean on a 2× print. */
const WEBP_QUALITY = 78;

mkdirSync(outDir, { recursive: true });
const wanted = new Set(GALLERY_ARTS.map((art) => `${art}.webp`));
for (const file of readdirSync(outDir)) {
  if (!wanted.has(file)) rmSync(resolve(outDir, file));
}

const oversized: string[] = [];
for (const file of wanted) {
  const output = resolve(outDir, file);
  // Lanczos downscale; sharp writes no metadata unless asked to.
  await sharp(resolve(artDir, file))
    .resize({ height: GALLERY_THUMB_HEIGHT, withoutEnlargement: true })
    .webp({ quality: WEBP_QUALITY, effort: 6, smartSubsample: true })
    .toFile(output);
  const bytes = statSync(output).size;
  console.log(`${file}: ${(bytes / 1024).toFixed(0)} KB`);
  if (bytes > GALLERY_THUMB_MAX_BYTES) oversized.push(file);
}

if (oversized.length > 0) throw new Error(`over ${GALLERY_THUMB_MAX_BYTES} bytes: ${oversized.join(", ")}`);
