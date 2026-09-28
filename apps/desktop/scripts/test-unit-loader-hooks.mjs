/**
 * Module loader hooks for the desktop unit test processes (see
 * `test-unit-loader.mjs`, which registers them).
 *
 * `@phosphor-icons/react`'s ESM entry is a barrel over roughly 6,000 small
 * modules (one component and one path table per icon). Vite tree-shakes it
 * for the app, but every `node --test` child process that renders a
 * component loads the whole graph, which costs about 3 s per file and was
 * most of the desktop suite's run time (#459). The package also ships the
 * same icons as one prebuilt CommonJS file; loading that instead takes about
 * 0.2 s and exposes every named export of the ESM entry.
 *
 * The bundle sits in a `"type": "module"` package, so Node would parse it as
 * ESM from its path alone; the load hook therefore hands its source over
 * explicitly as CommonJS. Its `require("react")` resolves to the same React
 * instance the tests import.
 */
import { readFile } from "node:fs/promises";

/**
 * The one specifier redirected to the CommonJS build. Only this exact bare
 * specifier is matched: a subpath import (`@phosphor-icons/react/ssr`,
 * `@phosphor-icons/react/dist/...`) still loads the ESM copy, next to the
 * CommonJS one, with its own `IconContext` instance. Keep icon imports bare.
 */
const prebundledSpecifier = "@phosphor-icons/react";
const prebundledMarker = "?shiori-test-prebundled";

/** Resolves the prebundled package to its CommonJS build, tagged for `load`. */
export async function resolve(specifier, context, nextResolve) {
  if (specifier !== prebundledSpecifier) return nextResolve(specifier, context);
  const resolved = await nextResolve(specifier, { ...context, conditions: ["node", "require"] });
  return { url: `${resolved.url}${prebundledMarker}`, format: "commonjs", shortCircuit: true };
}

/** Serves a tagged bundle as CommonJS source regardless of its package type. */
export async function load(url, context, nextLoad) {
  if (!url.endsWith(prebundledMarker)) return nextLoad(url, context);
  const source = await readFile(new URL(url.slice(0, -prebundledMarker.length)), "utf8");
  return { format: "commonjs", source, shortCircuit: true };
}
