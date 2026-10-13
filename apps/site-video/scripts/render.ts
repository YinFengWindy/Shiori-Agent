/**
 * Renders every demo clip (the ids of apps/site/src/content/showcase.ts) as
 * video: `<id>.webm` (VP9, what browsers pick first) and `<id>.mp4` (H.264,
 * for browsers without VP9), in apps/site-video/out/ (not committed).
 *
 * The website does not show the videos any more (#790: on slow or flaky
 * lines they stalled and crowded out the page's pictures); it shows one
 * still per feature, captured from the real app by scripts/stills.ts. This keeps the clips
 * renderable for whenever a page wants them again (`pnpm run site:video`).
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
import { ensureBrowser, renderMedia, selectComposition } from "@remotion/renderer";
import { CLIP_MAX_BYTES } from "../src/clips";
import { clipIdsFromArgs } from "./clipArgs";

const here = dirname(fileURLToPath(import.meta.url));
const entryPoint = resolve(here, "../src/index.ts");
const outDir = resolve(here, "../out");

/**
 * Encoder quality per format (lower is better and larger). Chosen so the
 * screenshots' text stays crisp at 1280×800 while every file fits the cap.
 */
const VP9_CRF = 42;
const H264_CRF = 28;

const clipIds = clipIdsFromArgs(process.argv.slice(2));
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
    if (bytes > CLIP_MAX_BYTES) oversized.push(file);
  }
}

if (oversized.length > 0) throw new Error(`over ${CLIP_MAX_BYTES} bytes: ${oversized.join(", ")}`);
