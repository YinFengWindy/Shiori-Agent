/**
 * Renders the website showcase's stills (#790): one frame of every demo clip
 * (the ids of apps/site/src/content/showcase.ts, at `CLIP_TIMING[id].stillSeconds`)
 * into `apps/site/src/assets/showcase/<id>.webp`, which the site shows in
 * place of the clip. The site build only reads those committed files; run
 * this (`pnpm run site:stills`) after changing a clip or its still moment and
 * commit the output.
 *
 * The frame is captured losslessly at the app screenshots' own size
 * (1440×900, the coordinate space every clip is laid out in: sharp text and
 * 2× the showcase's largest CSS width) and encoded to WebP with sharp, so
 * the quality is ours to set; Remotion's own WebP stills have a fixed one.
 * Each file must fit `SHOWCASE_STILL_MAX_BYTES`, which the site's build test
 * checks too.
 *
 * Remotion renders in Chrome Headless Shell: `ensureBrowser()` downloads it
 * into apps/site-video/node_modules/.remotion on the first run.
 *
 * Usage: `tsx scripts/stills.ts [clip id ...]` (default: every clip).
 */
import { mkdirSync, mkdtempSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { bundle } from "@remotion/bundler";
import { ensureBrowser, renderStill, selectComposition } from "@remotion/renderer";
import sharp from "sharp";
import { SHOWCASE_STILL_MAX_BYTES } from "../../site/src/content/showcase";
import { CLIP_FORMAT, CLIP_TIMING } from "../src/clips";
import { clipIdsFromArgs } from "./clipArgs";

const here = dirname(fileURLToPath(import.meta.url));
const entryPoint = resolve(here, "../src/index.ts");
const outDir = resolve(here, "../../site/src/assets/showcase");

/** The screenshots' width, which the clips scale down to `CLIP_FORMAT.width`: render back up to it. */
const STILL_WIDTH = 1440;
/** WebP quality: UI text stays crisp while every still fits the byte budget. */
const WEBP_QUALITY = 80;

const clipIds = clipIdsFromArgs(process.argv.slice(2));
mkdirSync(outDir, { recursive: true });
const scratch = mkdtempSync(join(tmpdir(), "shiori-stills-"));
try {
  await ensureBrowser();
  const serveUrl = await bundle({ entryPoint });
  const oversized: string[] = [];
  for (const id of clipIds) {
    const composition = await selectComposition({ serveUrl, id });
    const png = join(scratch, `${id}.png`);
    await renderStill({
      serveUrl,
      composition,
      frame: Math.round(CLIP_TIMING[id].stillSeconds * composition.fps),
      imageFormat: "png",
      scale: STILL_WIDTH / CLIP_FORMAT.width,
      output: png,
    });
    const output = resolve(outDir, `${id}.webp`);
    // sharp writes no metadata unless asked to.
    await sharp(png).webp({ quality: WEBP_QUALITY, effort: 6, smartSubsample: true }).toFile(output);
    const bytes = statSync(output).size;
    console.log(`${id}.webp: ${(bytes / 1024).toFixed(0)} KB`);
    if (bytes > SHOWCASE_STILL_MAX_BYTES) oversized.push(`${id}.webp`);
  }
  if (oversized.length > 0) throw new Error(`over ${SHOWCASE_STILL_MAX_BYTES} bytes: ${oversized.join(", ")}`);
} finally {
  rmSync(scratch, { recursive: true, force: true });
}
