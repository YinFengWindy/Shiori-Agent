/**
 * `--import` entry for the desktop unit test processes: registers
 * `test-unit-loader-hooks.mjs` in every `node --test` child before any test
 * file loads, then settles Base UI's load-time environment probes.
 */
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import { registerTestModuleHooks } from "./test-unit-loader-hooks.mjs";
import { esmEntryTarget, readPackageManifest, sdkPackageRequire } from "./test-unit-packages.mjs";

registerTestModuleHooks();

/** Base UI's utility modules that answer an environment question at load time. */
const baseUiProbeSubpaths = ["./useIsoLayoutEffect", "./platform"];

/** Fails the test process with the fix to make, rather than an opaque TypeError. */
function baseUiProbeError(detail) {
  return new Error(`test-unit-loader: ${detail}. A Base UI upgrade changed its internal environment probe modules; update settleBaseUiEnvironmentProbes() in apps/desktop/scripts/test-unit-loader.mjs to match.`);
}

/**
 * ESM URLs of the probe modules in the very Base UI copy the plugin SDK
 * loads (the SDK owns `Select` and `ActionMenu`), so a second copy elsewhere
 * in the tree cannot be settled in its place. The prebundled Base UI
 * (`test-unit-prebundle.mjs`) leaves `@base-ui/utils` external and imports
 * these same files.
 */
async function baseUiProbeUrls() {
  const baseUiManifestPath = (await sdkPackageRequire()).resolve("@base-ui/react/package.json");
  const utilsManifestPath = createRequire(baseUiManifestPath).resolve("@base-ui/utils/package.json");
  const utilsManifest = await readPackageManifest(utilsManifestPath);
  if (!utilsManifest.exports || typeof utilsManifest.exports !== "object") throw baseUiProbeError(`${utilsManifestPath} has no "exports" map`);
  return baseUiProbeSubpaths.map((subpath) => {
    const target = esmEntryTarget(utilsManifest, subpath);
    if (target === undefined) throw baseUiProbeError(`@base-ui/utils no longer exports an ESM "${subpath}"`);
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
