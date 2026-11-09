import { build } from "esbuild";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { basename, dirname, extname, join } from "node:path";

const hostPeers = /^(?:react(?:-dom)?(?:\/|$)|@yinfengwindy\/shiori-sdk(?:\/|$))/;

/** Emits Vite-style URL imports without executing raw JS/WASM/model assets. */
export function pluginRendererAssets(destination) {
  const emitted = new Map();
  return {
    name: "shiori-plugin-url-assets",
    setup(builder) {
      builder.onResolve({ filter: /\?(?:worker&)?url$/ }, async (args) => {
        const worker = args.path.endsWith("?worker&url");
        const request = args.path.slice(0, args.path.indexOf("?"));
        const resolved = await builder.resolve(request, { importer: args.importer, resolveDir: args.resolveDir, kind: args.kind });
        if (resolved.errors.length) return { errors: resolved.errors };
        if (resolved.external || !resolved.path) return { errors: [{ text: `URL asset must resolve to a local file: ${request}` }] };
        return { path: resolved.path, namespace: worker ? "shiori-worker-url" : "shiori-asset-url" };
      });
      for (const namespace of ["shiori-worker-url", "shiori-asset-url"]) {
        builder.onLoad({ filter: /.*/, namespace }, async ({ path }) => {
          const worker = namespace === "shiori-worker-url", key = `${namespace}:${path}`;
          let asset = emitted.get(key);
          if (!asset) { asset = emit(path, worker); emitted.set(key, asset); }
          return { contents: `export default ${JSON.stringify(await asset)};`, loader: "js", watchFiles: [path] };
        });
      }
    },
  };

  async function emit(path, worker) {
    const contents = worker ? await bundleWorker(path) : await readFile(path);
    const extension = worker ? ".js" : extname(path);
    const name = basename(path, extname(path)).replace(/[^a-zA-Z0-9_-]/g, "_");
    const hash = createHash("sha256").update(contents).digest("hex").slice(0, 16);
    const relative = `assets/${name}-${hash}${extension}`;
    const output = join(destination, "renderer", relative);
    await mkdir(dirname(output), { recursive: true });
    await writeFile(output, contents);
    // The importing plugin resolves this against frontend.mjs's admitted URL.
    return `./${relative}`;
  }
}

/** Workers own their runtime and cannot borrow renderer-only SDK/React globals. */
export async function bundleWorker(entry) {
  const result = await build({
    entryPoints: [entry], outfile: "worker.js", bundle: true, write: false,
    format: "iife", platform: "browser", target: "es2022",
    plugins: [{ name: "shiori-worker-peer-boundary", setup(builder) {
      builder.onResolve({ filter: hostPeers }, ({ path }) => ({ errors: [{ text: `Worker cannot import a host UI peer: ${path}` }] }));
    } }],
  });
  if (result.outputFiles.length !== 1) throw new Error("Worker URL imports must produce one self-contained script");
  return result.outputFiles[0].contents;
}
