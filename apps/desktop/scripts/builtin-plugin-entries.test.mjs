import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { createServer } from "vite";
import { builtinPluginEntries, builtinPluginEntrySource } from "./builtin-plugin-entries.mjs";

test("all three registries import only builtins and react to development manifest changes", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "plugin-entries-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  for (const id of ["bundled", "separate"]) {
    await mkdir(join(root, id));
    await writeFile(join(root, id, "manifest.yaml"), `api: 2\nid: ${id}\n${id === "separate" ? "distribution: external\n" : ""}`, "utf8");
    for (const [kind, extension] of [["ui", "tsx"], ["background", "ts"], ["surface", "tsx"]]) {
      await mkdir(join(root, id, kind));
      await writeFile(join(root, id, kind, `index.${extension}`), "INVALID source must not be parsed during inventory", "utf8");
    }
  }
  for (const kind of ["ui", "background", "surface"]) {
    const entry = await builtinPluginEntrySource(root, kind);
    assert.equal(entry.paths.length, 1);
    assert.ok(entry.code.includes("bundled"));
    assert.ok(!entry.code.includes("separate"));
  }
  const watcher = new EventEmitter();
  const watched = [];
  watcher.add = (path) => watched.push(path);
  const invalidated = [], sent = [];
  const server = { watcher, httpServer: new EventEmitter(), moduleGraph: { getModuleById: (id) => id, invalidateModule: (id) => invalidated.push(id) }, ws: { send: (event) => sent.push(event) } };
  const plugin = builtinPluginEntries(root);
  plugin.configureServer(server);
  assert.deepEqual(watched, [root], "inventory changes are watched without importing the directory");
  await writeFile(join(root, "bundled/manifest.yaml"), "distribution: external\n", "utf8");
  watcher.emit("change", join(root, "bundled/manifest.yaml"));
  assert.equal(invalidated.length, 3);
  assert.deepEqual(sent, [{ type: "full-reload" }]);
  assert.deepEqual((await builtinPluginEntrySource(root, "ui")).paths, []);
  watcher.emit("add", join(root, "bundled/surface/index.tsx"));
  assert.equal(invalidated.length, 6, "new source entries refresh the generated import inventory");
  server.httpServer.emit("close");
  assert.equal(watcher.listenerCount("change"), 0);
});

test("the Vite client and SSR loaders resolve all registries and exclude external entries", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "plugin-entries-dev-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  const rendererRoot = join(root, "renderer");
  await mkdir(rendererRoot);
  for (const id of ["bundled", "separate"]) {
    await mkdir(join(root, "plugins", id), { recursive: true });
    await writeFile(join(root, "plugins", id, "manifest.yaml"), `distribution: ${id === "bundled" ? "builtin" : "external"}\n`, "utf8");
    for (const [kind, extension] of [["ui", "tsx"], ["background", "ts"], ["surface", "tsx"]]) {
      await mkdir(join(root, "plugins", id, kind));
      await writeFile(join(root, "plugins", id, kind, `index.${extension}`), id === "bundled" ? `export default {marker:'${kind}'};` : "INVALID EXTERNAL JAVASCRIPT !!!", "utf8");
    }
  }
  const server = await createServer({ root: rendererRoot, configFile: false, logLevel: "silent", plugins: [builtinPluginEntries(join(root, "plugins"))], server: { middlewareMode: true, preTransformRequests: false, fs: { allow: [root] } }, optimizeDeps: { noDiscovery: true, include: [] } });
  try {
    for (const kind of ["ui", "background", "surface"]) {
      await t.test(kind, async () => {
        const id = `virtual:shiori-builtin-plugins/${kind}`;
        await writeFile(join(rendererRoot, `${kind}.ts`), `export { default } from ${JSON.stringify(id)};`, "utf8");
        // Browser imports register the virtual module before its load hook runs.
        // A direct virtual request alone misses addWatchFile import-analysis failures.
        await server.transformRequest(`/${kind}.ts`);
        const transformed = await server.transformRequest(id);
        assert.ok(transformed.code.includes("/plugins/bundled/"));
        assert.ok(!transformed.code.includes("separate"));
        const imported = await server.ssrLoadModule(id);
        assert.equal(Object.keys(imported.default).length, 1);
        assert.equal(Object.values(imported.default)[0].default.marker, kind);
      });
    }
  } finally { await server.close(); }
});
