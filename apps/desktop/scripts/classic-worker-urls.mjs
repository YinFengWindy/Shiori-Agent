import { createHash } from "node:crypto";
import { bundleWorker } from "../../../scripts/plugin-renderer-assets.mjs";

const modulePrefix = "\0shiori-classic-worker:";
const urlPrefix = "/@shiori-classic-worker/";

/** Keep ?worker&url classic in dev, as in production and external plugin builds. */
export function classicWorkerUrls() {
  const entries = new Map();
  return {
    name: "shiori-classic-worker-urls",
    apply: "serve",
    enforce: "pre",
    async resolveId(id, importer) {
      if (!id.endsWith("?worker&url")) return;
      const resolved = await this.resolve(id.slice(0, -"?worker&url".length), importer, { skipSelf: true });
      if (!resolved || resolved.external) this.error(`Worker must resolve to a local file: ${id}`);
      const key = createHash("sha256").update(resolved.id).digest("hex");
      entries.set(`${urlPrefix}${key}.js`, resolved.id);
      // A virtual ID prevents Vite's worker transform from returning an ESM URL.
      return `${modulePrefix}${key}`;
    },
    load(id) {
      if (!id.startsWith(modulePrefix)) return;
      return `export default ${JSON.stringify(`${urlPrefix}${id.slice(modulePrefix.length)}.js`)};`;
    },
    configureServer(server) {
      server.middlewares.use(async (request, response, next) => {
        const pathname = request.url?.split("?")[0];
        if (!pathname?.startsWith(urlPrefix)) return next();
        // Only serve entries resolved through a source import, never request paths.
        const entry = entries.get(pathname);
        if (!entry) { response.statusCode = 404; response.end(); return; }
        try {
          // Rebuild on startup so editing a worker dependency cannot reuse stale code.
          const contents = await bundleWorker(entry);
          response.setHeader("Content-Type", "text/javascript");
          response.setHeader("Cache-Control", "no-store");
          response.end(contents);
        } catch (error) { next(error); }
      });
    },
  };
}
