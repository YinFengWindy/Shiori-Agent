import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { mkdtemp, mkdir, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { createServer } from "vite";
import { builtinPluginEntries, builtinPluginEntrySource } from "./builtin-plugin-entries.mjs";

test("the builtin inventory discovers each declared frontend exactly once", async () => {
  const pluginsRoot = fileURLToPath(new URL("../../../plugins", import.meta.url));
  const entry = await builtinPluginEntrySource(pluginsRoot);
  assert.ok(entry.paths.includes(join(pluginsRoot, "grok_bot", "frontend.ts")));
  assert.equal(entry.paths.filter((path) => path.includes("desktop_pet")).length, 1);
});

test("one inventory tracks manifests and declared entry changes", async (t) => {
  const root = await mkdtemp(join(tmpdir(), "plugin-entries-"));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(join(root, "bundled"));
  await writeFile(join(root, "bundled/manifest.yaml"), "frontend: {entry: custom.ts}\n", "utf8");
  await writeFile(join(root, "bundled/custom.ts"), "export const ui = {};", "utf8");
  assert.equal((await builtinPluginEntrySource(root)).paths.length, 1);
  const watcher = new EventEmitter();
  watcher.add = () => {};
  const invalidated = [], sent = [];
  const server = { watcher, httpServer: new EventEmitter(), moduleGraph: { getModuleById: (id) => id, invalidateModule: (id) => invalidated.push(id) }, ws: { send: (event) => sent.push(event) } };
  builtinPluginEntries(root).configureServer(server);
  await writeFile(join(root, "bundled/manifest.yaml"), "distribution: external\n", "utf8");
  watcher.emit("change", join(root, "bundled/manifest.yaml"));
  assert.deepEqual(sent, [{ type: "full-reload" }]);
  assert.deepEqual((await builtinPluginEntrySource(root)).paths, []);
  watcher.emit("add", join(root, "bundled/new-entry.ts"));
  assert.equal(invalidated.length, 2);
  server.httpServer.emit("close");
  assert.equal(watcher.listenerCount("change"), 0);
});

test("Vite loads one namespace with three contributions and never parses external source", async (t) => {
  const root = await realpath(await mkdtemp(join(tmpdir(), "plugin-entries-dev-")));
  t.after(() => rm(root, { recursive: true, force: true }));
  const rendererRoot = join(root, "renderer");
  await mkdir(rendererRoot);
  for (const id of ["bundled", "separate"]) {
    await mkdir(join(root, "plugins", id), { recursive: true });
    await writeFile(join(root, "plugins", id, "manifest.yaml"), `distribution: ${id === "bundled" ? "builtin" : "external"}\nfrontend: {entry: custom.ts}\n`, "utf8");
    await writeFile(join(root, "plugins", id, "custom.ts"), id === "bundled" ? "export const ui = {marker:'ui'}; export const background = {marker:'background'}; export const surface = {marker:'surface'};" : "INVALID EXTERNAL JAVASCRIPT !!!", "utf8");
  }
  const server = await createServer({ root: rendererRoot, configFile: false, logLevel: "silent", plugins: [builtinPluginEntries(join(root, "plugins"))], server: { middlewareMode: true, preTransformRequests: false, fs: { allow: [root] } }, optimizeDeps: { noDiscovery: true, include: [] } });
  try {
    const id = "virtual:shiori-builtin-plugins";
    await writeFile(join(rendererRoot, "entry.ts"), `export { default } from ${JSON.stringify(id)};`, "utf8");
    await server.transformRequest("/entry.ts");
    const imported = await server.ssrLoadModule(id);
    assert.equal(Object.keys(imported.default).length, 1);
    const namespace = Object.values(imported.default)[0];
    assert.deepEqual([namespace.ui.marker, namespace.background.marker, namespace.surface.marker], ["ui", "background", "surface"]);
  } finally { await server.close(); }
});
