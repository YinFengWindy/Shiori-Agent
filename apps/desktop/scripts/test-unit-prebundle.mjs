/**
 * Prebundles the desktop unit tests' largest third-party ESM graphs once per
 * run, before any `node --test` child starts.
 *
 * Every test file runs in its own process and loads its imports from scratch,
 * so a package's module count is paid once per file. Base UI (since #504 the
 * plugin SDK entry serves `Select` and `ActionMenu`, so almost every renderer
 * test loads it) and happy-dom (the DOM harness) are several hundred small
 * modules each, and resolving and evaluating them was most of a DOM test's
 * startup. esbuild folds each package into a few files here; the loader hooks
 * (`test-unit-loader-hooks.mjs`) then serve those files wherever Node would
 * have loaded the package's own entry.
 *
 * React and React DOM stay external, so tests and bundles share one React.
 * `@base-ui/utils` stays external too: `test-unit-loader.mjs` evaluates two of
 * its modules by URL before any test loads, and the bundle has to import those
 * very instances.
 */
import { writeFile } from "node:fs/promises";
import { isBuiltin } from "node:module";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";
import { build } from "esbuild";
import { esmEntryTarget, readPackageManifest, sdkPackageRequire } from "./test-unit-packages.mjs";

/** Packages served from a prebundle, with the packages each one leaves external. */
const prebundledPackages = [
  { name: "@base-ui/react", directory: "base-ui-react", external: ["@base-ui/utils"] },
  { name: "happy-dom", directory: "happy-dom", external: [] },
];

/** Packages no bundle may inline, so every test process keeps one instance. */
const sharedExternals = ["react", "react-dom"];

/**
 * Bundles keep the CommonJS `require` calls of the dependencies they inline
 * (happy-dom's `ws`, Base UI's `use-sync-external-store`); ESM output has no
 * `require` of its own, so each output file gets one.
 */
const requireBanner = 'import { createRequire as __shioriTestCreateRequire } from "node:module"; const require = __shioriTestCreateRequire(import.meta.url);';

/**
 * Builds every prebundled package into `outDir` and writes the redirect table
 * (original entry file URL → bundled entry file URL) there.
 *
 * Returns the table's path, to hand to the test processes through
 * `prebundleManifestEnv` (`test-unit-loader-hooks.mjs`).
 */
export async function prebundleTestDependencies(outDir) {
  const sdkRequire = await sdkPackageRequire();
  const redirects = {};
  for (const prebundled of prebundledPackages) {
    const manifestPath = sdkRequire.resolve(`${prebundled.name}/package.json`);
    const packageRoot = dirname(manifestPath);
    const bundleRoot = join(outDir, prebundled.directory);
    const manifest = await readPackageManifest(manifestPath);
    const entries = packageEntries(manifest).map(({ subpath, target }) => ({
      source: join(packageRoot, target),
      out: subpath === "." ? "index" : `${subpath.slice(2)}/index`,
    }));
    await build({
      entryPoints: entries.map(({ source, out }) => ({ in: source, out })),
      outdir: bundleRoot,
      outExtension: { ".js": ".mjs" },
      bundle: true,
      splitting: true,
      format: "esm",
      platform: "node",
      // Node ≥ 22.12 resolves `module-sync`; esbuild adds node/import/require/default itself.
      conditions: ["module-sync"],
      banner: { js: requireBanner },
      plugins: [bundledPackageResolution([...sharedExternals, ...prebundled.external])],
      logLevel: "error",
    });
    for (const { source, out } of entries) {
      redirects[pathToFileURL(source).href] = pathToFileURL(join(bundleRoot, `${out}.mjs`)).href;
    }
  }
  const redirectsPath = join(outDir, "redirects.json");
  await writeFile(redirectsPath, JSON.stringify(redirects), "utf8");
  return redirectsPath;
}

/** Every ESM JavaScript entry the package exports (wildcard subpaths excluded). */
function packageEntries(manifest) {
  const subpaths = manifest.exports && typeof manifest.exports === "object" && Object.keys(manifest.exports).some((key) => key.startsWith("."))
    ? Object.keys(manifest.exports).filter((key) => !key.includes("*") && key !== "./package.json")
    : ["."];
  return subpaths.flatMap((subpath) => {
    const target = esmEntryTarget(manifest, subpath);
    return target && /\.m?js$/.test(target) ? [{ subpath, target }] : [];
  });
}

/**
 * Resolution rules for the bundled packages' bare imports.
 *
 * `externalNames` (and their subpaths) stay out of the bundle, imported from
 * the exact file the inlined code would have resolved: a file URL for
 * `import`, a path for `require`. The bundles live outside the repository,
 * where a bare specifier would not resolve, and a file address also
 * guarantees the bundle shares the instance the tests load.
 *
 * Any other import that does not resolve stays as written: some exported
 * subpaths need packages that are not installed (Base UI's date adapters want
 * `date-fns` or `luxon`). Without the bundle that import fails only when the
 * code needing it loads, and so it does with the bundle.
 */
function bundledPackageResolution(externalNames) {
  const escaped = externalNames.map((name) => name.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&"));
  const external = new RegExp(`^(?:${escaped.join("|")})(?:/|$)`);
  const nested = Symbol("shiori-test-resolution");
  return {
    name: "shiori-test-resolution",
    setup(pluginBuild) {
      // Bare specifiers only: relative imports inside a package always resolve.
      pluginBuild.onResolve({ filter: /^[^./]/ }, async (args) => {
        if (args.pluginData === nested || isBuiltin(args.path)) return undefined;
        const resolved = await pluginBuild.resolve(args.path, {
          kind: args.kind,
          importer: args.importer,
          resolveDir: args.resolveDir,
          pluginData: nested,
        });
        const isExternal = external.test(args.path);
        if (resolved.errors.length) return isExternal ? { errors: resolved.errors } : { path: args.path, external: true };
        if (!isExternal) return undefined;
        const path = args.kind === "require-call" ? resolved.path : pathToFileURL(resolved.path).href;
        return { path, external: true };
      });
    },
  };
}
