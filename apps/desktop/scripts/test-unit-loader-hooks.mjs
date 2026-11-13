/**
 * Module loader hooks for the desktop unit test processes (see
 * `test-unit-loader.mjs`, which registers them).
 *
 * They run in-thread through `module.registerHooks`. tsx already resolves and
 * loads in-thread on the Node versions this repository uses; a hook added with
 * the asynchronous `module.register` would move every import of every test
 * process onto a separate loader thread, which made a test file's startup
 * about a third slower.
 *
 * Two redirections, both because each test file is its own process and pays
 * for its imports' module count again:
 *
 * - `@phosphor-icons/react`'s ESM entry is a barrel over roughly 6,000 small
 *   modules (one component and one path table per icon). Vite tree-shakes it
 *   for the app, but every test process that renders a component would load
 *   the whole graph, about 3 s per file (#459). The package also ships the
 *   same icons as one prebuilt CommonJS file, which exposes every named export
 *   of the ESM entry. It sits in a `"type": "module"` package, so Node would
 *   parse it as ESM from its path alone; the load hook hands its source over
 *   explicitly as CommonJS. Its `require("react")` resolves to the same React
 *   instance the tests import.
 * - Base UI and happy-dom are served from the bundles `test-unit-prebundle.mjs`
 *   builds once per run, when the runner passes their redirect table.
 */
import { readFileSync } from "node:fs";
import { registerHooks } from "node:module";

/**
 * The one specifier redirected to the CommonJS build. Only this exact bare
 * specifier is matched: a subpath import (`@phosphor-icons/react/ssr`,
 * `@phosphor-icons/react/dist/...`) still loads the ESM copy, next to the
 * CommonJS one, with its own `IconContext` instance. Keep icon imports bare.
 */
const commonJsBuildSpecifier = "@phosphor-icons/react";
const commonJsBuildMarker = "?shiori-test-commonjs";

/**
 * Environment variable through which the runner hands every test process the
 * path of the prebundle redirect table (see `test-unit-prebundle.mjs`).
 */
export const prebundleManifestEnv = "SHIORI_DESKTOP_TEST_PREBUNDLE";

/**
 * Original entry file URL → bundled entry file URL. Matching on the resolved
 * file rather than the specifier sends every import of the same entry to one
 * bundle instance, and leaves any other copy of the package alone. Empty when
 * a test process was started without the runner (no redirect table).
 */
const prebundleRedirects = new Map(Object.entries(
  process.env[prebundleManifestEnv] ? JSON.parse(readFileSync(process.env[prebundleManifestEnv], "utf8")) : {},
));

/** Registers the hooks in the calling thread. */
export function registerTestModuleHooks() {
  registerHooks({ resolve, load });
}

function resolve(specifier, context, nextResolve) {
  if (specifier === commonJsBuildSpecifier) {
    const resolved = nextResolve(specifier, { ...context, conditions: ["node", "require"] });
    return { url: `${resolved.url}${commonJsBuildMarker}`, format: "commonjs", shortCircuit: true };
  }
  const resolved = nextResolve(specifier, context);
  const bundled = prebundleRedirects.get(resolved.url);
  return bundled ? { url: bundled, format: "module", shortCircuit: true } : resolved;
}

function load(url, context, nextLoad) {
  if (!url.endsWith(commonJsBuildMarker)) return nextLoad(url, context);
  const source = readFileSync(new URL(url.slice(0, -commonJsBuildMarker.length)), "utf8");
  return { format: "commonjs", source, shortCircuit: true };
}
