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
  const selectPath = fileURLToPath(import.meta.resolve("@base-ui/react/select"));
  const utilsManifestPath = createRequire(selectPath).resolve("@base-ui/utils/package.json");
  const { exports } = JSON.parse(await readFile(utilsManifestPath, "utf8"));
  const probeUrls = ["./useIsoLayoutEffect", "./platform"].map((subpath) =>
    pathToFileURL(join(dirname(utilsManifestPath), exports[subpath].import.default)).href);
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
