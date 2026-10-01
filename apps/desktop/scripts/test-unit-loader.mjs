/**
 * `--import` entry for the desktop unit test processes: registers
 * `test-unit-loader-hooks.mjs` in every `node --test` child before any test
 * file loads, then settles Base UI's load-time environment probes.
 */
import { readFile } from "node:fs/promises";
import { createRequire, register } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

register("./test-unit-loader-hooks.mjs", import.meta.url);

/** Base UI's utility modules that answer an environment question at load time. */
const baseUiProbeSubpaths = ["./useIsoLayoutEffect", "./platform"];

/** Fails the test process with the fix to make, rather than an opaque TypeError. */
function baseUiProbeError(detail) {
  return new Error(`test-unit-loader: ${detail}. A Base UI upgrade changed its internal environment probe modules; update settleBaseUiEnvironmentProbes() in apps/desktop/scripts/test-unit-loader.mjs to match.`);
}

/**
 * ESM URLs of the probe modules in the very Base UI copy the plugin SDK
 * loads: resolved from the SDK package itself (which owns `Select` and
 * `ActionMenu`), so a second copy elsewhere in the tree cannot be settled
 * in its place.
 */
async function baseUiProbeUrls() {
  // The main entry is `src/index.ts`, one level below the package root.
  const sdkManifestPath = join(dirname(fileURLToPath(import.meta.resolve("@shiori/sdk"))), "..", "package.json");
  if (JSON.parse(await readFile(sdkManifestPath, "utf8")).name !== "@shiori/sdk") {
    throw new Error(`test-unit-loader: ${sdkManifestPath} is not the plugin SDK manifest; the SDK main entry moved, update baseUiProbeUrls().`);
  }
  const baseUiManifestPath = createRequire(sdkManifestPath).resolve("@base-ui/react/package.json");
  const utilsManifestPath = createRequire(baseUiManifestPath).resolve("@base-ui/utils/package.json");
  const { exports } = JSON.parse(await readFile(utilsManifestPath, "utf8"));
  if (!exports || typeof exports !== "object") throw baseUiProbeError(`${utilsManifestPath} has no "exports" map`);
  return baseUiProbeSubpaths.map((subpath) => {
    const target = exports[subpath]?.import?.default;
    if (typeof target !== "string") throw baseUiProbeError(`@base-ui/utils no longer exports an ESM "${subpath}"`);
    return pathToFileURL(join(dirname(utilsManifestPath), target)).href;
  });
}

/**
 * Base UI answers two questions once, when its utility modules first load:
 * whether layout effects run at all (`useIsoLayoutEffect`: is there a
 * `document`?) and whether it runs under a test DOM (`platform.env.jsdom`,
 * from `navigator.userAgent`, which relaxes pointer checks happy-dom cannot
 * satisfy). The DOM harness installs a happy-dom window per mount, so a test
 * process that loads Base UI before its first mount locks in the no-DOM
 * answers and its selects and menus stop responding. Since the plugin SDK
 * (#440) serves `Select` and `ActionMenu` from the same entry as the shared
 * class names, almost every renderer module loads Base UI, so a test can no
 * longer defer it with a dynamic import.
 *
 * Evaluate just those probe modules here, under the answers a mounted
 * happy-dom window gives (its user agent and platform), before any test file
 * loads; the stand-in globals are removed right after, so nothing else sees
 * them. Importing happy-dom itself here would cost every test process ~0.2 s.
 */
async function settleBaseUiEnvironmentProbes() {
  const probeUrls = await baseUiProbeUrls();
  const standIns = {
    document: {},
    navigator: {
      userAgent: "Mozilla/5.0 (X11; Win32 x64) AppleWebKit/537.36 (KHTML, like Gecko) HappyDOM",
      platform: "X11; Win32 x64",
      maxTouchPoints: 0,
    },
  };
  const saved = Object.fromEntries(Object.keys(standIns).map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]));
  for (const [name, value] of Object.entries(standIns)) {
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value });
  }
  try {
    for (const url of probeUrls) await import(url);
  } finally {
    for (const [name, descriptor] of Object.entries(saved)) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else Reflect.deleteProperty(globalThis, name);
    }
  }
}

await settleBaseUiEnvironmentProbes();
