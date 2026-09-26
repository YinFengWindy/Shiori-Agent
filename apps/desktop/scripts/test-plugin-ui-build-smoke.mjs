#!/usr/bin/env node
/**
 * Reproducible build smoke check for the three plugin globs:
 * `renderer/src/plugins/pluginUiModules.ts` (main-window slots),
 * `renderer/src/surface/pluginSurfaceModules.ts` (plugin-owned desktop
 * windows, #181) and `renderer/src/background/pluginBackgroundModules.ts`
 * (headless always-resident background code, #226 item 1).
 *
 * The repo has built-in plugin UI entries, but may have no surface or
 * background entries. This script creates
 * a throwaway plugin under the real top-level `plugins/` tree carrying all
 * three entry points, each with its own recognizable marker, runs a real
 * renderer build against it, asserts all three markers made it into the
 * bundled output, and removes the throwaway plugin directory afterwards (on
 * success or failure) so it is safe to re-run repeatedly on a clean checkout.
 *
 * The three markers are checked separately on purpose: the surface entry
 * lands in a *different* rollup entry (`surface.html`) from the UI one, and
 * the background entry in yet another (`plugin-host.html`), so a single
 * combined check would let a broken glob hide behind the other two working.
 */
import { randomUUID } from "node:crypto";
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build as viteBuild } from "vite";

const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");
const repoRoot = resolve(desktopRoot, "..", "..");

const suffix = randomUUID().replace(/-/g, "").slice(0, 12);
const marker = `PLUGIN_UI_BUILD_SMOKE_${suffix}`;
const surfaceMarker = `PLUGIN_SURFACE_BUILD_SMOKE_${suffix}`;
const backgroundMarker = `PLUGIN_BACKGROUND_BUILD_SMOKE_${suffix}`;
const pluginId = `plugin_ui_build_smoke_${suffix}`;
const pluginDir = join(repoRoot, "plugins", pluginId);
const uiDir = join(pluginDir, "ui");
const surfaceDir = join(pluginDir, "surface");
const backgroundDir = join(pluginDir, "background");

/** Recursively searches built JS output for the marker string. */
async function bundleContainsMarker(dir, needle) {
  const entries = await readdir(dir, { withFileTypes: true });
  for (const entry of entries) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (await bundleContainsMarker(path, needle)) return true;
      continue;
    }
    if (!/\.m?js$/.test(entry.name)) continue;
    const content = await readFile(path, "utf-8");
    if (content.includes(needle)) return true;
  }
  return false;
}

async function main() {
  await mkdir(uiDir, { recursive: true });
  await writeFile(
    join(uiDir, "index.tsx"),
    [
      "// Throwaway fixture written by test-plugin-ui-build-smoke.mjs; not meant to be committed.",
      `const MARKER = ${JSON.stringify(marker)};`,
      "",
      "export default {",
      `  pluginId: ${JSON.stringify(pluginId)},`,
      "  settingsSection: { kind: \"component\", label: MARKER, component: () => null },",
      "  navPage: { label: MARKER, component: () => null },",
      "};",
      "",
    ].join("\n"),
    "utf-8",
  );

  await mkdir(surfaceDir, { recursive: true });
  await writeFile(
    join(surfaceDir, "index.tsx"),
    [
      "// Throwaway fixture written by test-plugin-ui-build-smoke.mjs; not meant to be committed.",
      `const MARKER = ${JSON.stringify(surfaceMarker)};`,
      "",
      "export default {",
      `  pluginId: ${JSON.stringify(pluginId)},`,
      "  surface: { component: () => MARKER },",
      "};",
      "",
    ].join("\n"),
    "utf-8",
  );

  await mkdir(backgroundDir, { recursive: true });
  await writeFile(
    join(backgroundDir, "index.ts"),
    [
      "// Throwaway fixture written by test-plugin-ui-build-smoke.mjs; not meant to be committed.",
      `const MARKER = ${JSON.stringify(backgroundMarker)};`,
      "",
      "export default {",
      `  pluginId: ${JSON.stringify(pluginId)},`,
      "  setup() { return MARKER; },",
      "};",
      "",
    ].join("\n"),
    "utf-8",
  );

  const outDir = await mkdtemp(join(tmpdir(), "plugin-ui-build-smoke-"));
  try {
    await viteBuild({
      configFile: resolve(desktopRoot, "renderer", "vite.config.ts"),
      logLevel: "warn",
      build: { outDir, emptyOutDir: true },
    });

    const checks = [
      { marker, glob: "plugins/<id>/ui/index.tsx", source: "pluginUiModules.ts" },
      { marker: surfaceMarker, glob: "plugins/<id>/surface/index.tsx", source: "pluginSurfaceModules.ts" },
      { marker: backgroundMarker, glob: "plugins/<id>/background/index.ts", source: "pluginBackgroundModules.ts" },
    ];
    for (const check of checks) {
      if (!(await bundleContainsMarker(outDir, check.marker))) {
        throw new Error(
          `expected marker ${check.marker} to appear in the built renderer bundle, but it did not. ` +
            `The ${check.glob} glob in ${check.source} is not matching real build output.`,
        );
      }
    }
    console.log(`[plugin-ui-build-smoke] passed: ui, surface and background markers for ${pluginId} found in the built bundle.`);
  } finally {
    await rm(outDir, { recursive: true, force: true });
  }
}

main()
  .catch((error) => {
    console.error("[plugin-ui-build-smoke] FAILED");
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await rm(pluginDir, { recursive: true, force: true });
  });
