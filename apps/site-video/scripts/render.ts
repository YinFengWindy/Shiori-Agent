/**
 * Renders every demo clip (src/clips.ts) into the website's assets:
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
import { DEMO_CLIPS } from "../src/clips";

const here = dirname(fileURLToPath(import.meta.url));
const entryPoint = resolve(here, "../src/index.ts");
const outDir = resolve(here, "../../site/src/assets/showcase");

/** Each video file must stay under this, so the showcase stays light on a phone. */
const MAX_VIDEO_BYTES = 1.5 * 1024 * 1024;

/**
 * Encoder quality per format (lower is better and larger). Chosen so the
 * screenshots' text stays crisp at 1280×800 while every file fits the cap.
 */
const VP9_CRF = 42;
const H264_CRF = 28;
const POSTER_JPEG_QUALITY = 82;

const requested = process.argv.slice(2);
const unknown = requested.filter((id) => !DEMO_CLIPS.some((clip) => clip.id === id));
if (unknown.length > 0) throw new Error(`unknown clip id: ${unknown.join(", ")}`);
const clips = requested.length > 0 ? DEMO_CLIPS.filter((clip) => requested.includes(clip.id)) : DEMO_CLIPS;

mkdirSync(outDir, { recursive: true });
await ensureBrowser();
const serveUrl = await bundle({ entryPoint });

const oversized: string[] = [];
for (const clip of clips) {
  const composition = await selectComposition({ serveUrl, id: clip.id });
  const outputs = [
    { file: `${clip.id}.webm`, codec: "vp9", crf: VP9_CRF },
    { file: `${clip.id}.mp4`, codec: "h264", crf: H264_CRF },
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
    if (bytes > MAX_VIDEO_BYTES) oversized.push(file);
  }
  const poster = resolve(outDir, `${clip.id}-poster.jpg`);
  await renderStill({
    serveUrl,
    composition,
    frame: Math.round(clip.posterSeconds * composition.fps),
    imageFormat: "jpeg",
    jpegQuality: POSTER_JPEG_QUALITY,
    output: poster,
  });
  console.log(`${clip.id}-poster.jpg: ${(statSync(poster).size / 1024).toFixed(0)} KB`);
}

if (oversized.length > 0) throw new Error(`over ${MAX_VIDEO_BYTES} bytes: ${oversized.join(", ")}`);
