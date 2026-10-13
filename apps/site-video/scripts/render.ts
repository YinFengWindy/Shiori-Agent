/**
 * Renders every demo clip (the ids of apps/site/src/content/showcase.ts) into
 * the website's assets:
 * `<id>.webm` (VP9, what browsers pick first), `<id>.mp4` (H.264, for
 * browsers without VP9) and `<id>-poster.jpg`, in
 * apps/site/src/assets/showcase/. The site build only reads those committed
 * files; run this (`pnpm run site:video`) after changing a clip and commit
 * the output.
 *
 * Remotion renders in Chrome Headless Shell: `ensureBrowser()` downloads it
 * into apps/site-video/node_modules/.remotion on the first run (about 120 MB,
 * once per install; it never runs on Vercel, which only builds the site).
 *
 * Usage: `tsx scripts/render.ts [clip id ...]` (default: every clip).
 */
import { mkdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { bundle } from "@remotion/bundler";
import { ensureBrowser, renderMedia, renderStill, selectComposition } from "@remotion/renderer";
import { SHOWCASE_CLIP_IDS, SHOWCASE_CLIP_MAX_BYTES, type ShowcaseClipId } from "../../site/src/content/showcase";
import { CLIP_TIMING } from "../src/clips";

const here = dirname(fileURLToPath(import.meta.url));
const entryPoint = resolve(here, "../src/index.ts");
const outDir = resolve(here, "../../site/src/assets/showcase");

/**
 * Encoder quality per format (lower is better and larger). Chosen so the
 * screenshots' text stays crisp at 1280×800 while every file fits the cap.
 */
const VP9_CRF = 42;
const H264_CRF = 28;
const POSTER_JPEG_QUALITY = 82;

const requested = process.argv.slice(2);
const isClipId = (id: string): id is ShowcaseClipId => (SHOWCASE_CLIP_IDS as readonly string[]).includes(id);
const unknown = requested.filter((id) => !isClipId(id));
if (unknown.length > 0) throw new Error(`unknown clip id: ${unknown.join(", ")}`);
const clipIds = requested.length > 0 ? requested.filter(isClipId) : SHOWCASE_CLIP_IDS;

mkdirSync(outDir, { recursive: true });
await ensureBrowser();
const serveUrl = await bundle({ entryPoint });

const oversized: string[] = [];
for (const id of clipIds) {
  const composition = await selectComposition({ serveUrl, id });
  const outputs = [
    { file: `${id}.webm`, codec: "vp9", crf: VP9_CRF },
    { file: `${id}.mp4`, codec: "h264", crf: H264_CRF },
  ] as const;
  for (const { file, codec, crf } of outputs) {
    const outputLocation = resolve(outDir, file);
    await renderMedia({
      serveUrl,
      composition,
      codec,
      crf,
      muted: true,
      imageFormat: "jpeg",
      jpegQuality: 95,
      pixelFormat: "yuv420p",
      ...(codec === "h264" ? { x264Preset: "slow" as const } : {}),
      outputLocation,
    });
    const bytes = statSync(outputLocation).size;
    console.log(`${file}: ${(bytes / 1024).toFixed(0)} KB`);
    if (bytes > SHOWCASE_CLIP_MAX_BYTES) oversized.push(file);
  }
  const poster = resolve(outDir, `${id}-poster.jpg`);
  await renderStill({
    serveUrl,
    composition,
    frame: Math.round(CLIP_TIMING[id].posterSeconds * composition.fps),
    imageFormat: "jpeg",
    jpegQuality: POSTER_JPEG_QUALITY,
    output: poster,
  });
  console.log(`${id}-poster.jpg: ${(statSync(poster).size / 1024).toFixed(0)} KB`);
}

if (oversized.length > 0) throw new Error(`over ${SHOWCASE_CLIP_MAX_BYTES} bytes: ${oversized.join(", ")}`);
