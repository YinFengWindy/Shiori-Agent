import assert from "node:assert/strict";
import { test } from "node:test";
import { createRuntimePluginBackgroundLoader } from "./runtimePluginBackground";
import { PluginBackgroundRegistry } from "./pluginBackgroundRegistry";

test("registers a well-formed external background entry into the shared registry", async () => {
  const registry = new PluginBackgroundRegistry();
  const events: string[] = [];
  const setup = () => {};
  const load = createRuntimePluginBackgroundLoader({
    importModule: async () => { events.push("import"); return { default: { pluginId: "demo", setup } }; },
    loadCss: async (url) => { events.push(`css ${url}`); return () => events.push(`remove ${url}`); },
    failed: () => assert.fail("unexpected failure"),
  }, registry);

  const registered = await load([{ pluginId: "demo", entry: "demo.mjs", css: ["demo.css"] }]);

  assert.deepEqual(registered, ["demo"]);
  assert.deepEqual(events, ["css demo.css", "import"]);
  assert.deepEqual(registry.get("demo"), { slot: "app.background", pluginId: "demo", setup });
});

test("reports a plugin id through succeeded once its background entry registers (#262)", async () => {
  const registry = new PluginBackgroundRegistry();
  const succeeded: string[] = [];
  const load = createRuntimePluginBackgroundLoader({
    importModule: async () => ({ default: { pluginId: "demo", setup: () => {} } }),
    loadCss: async () => () => {},
    succeeded: (pluginId) => succeeded.push(pluginId),
    failed: () => assert.fail("unexpected failure"),
  }, registry);

  await load([{ pluginId: "demo", entry: "demo.mjs", css: [] }]);

  assert.deepEqual(succeeded, ["demo"]);
});

test("a malformed module removes its loaded CSS and is reported, not registered", async () => {
  const registry = new PluginBackgroundRegistry();
  const removed: string[] = [];
  const failures: unknown[] = [];
  const load = createRuntimePluginBackgroundLoader({
    importModule: async () => ({ default: { pluginId: "demo" /* no setup() */ } }),
    loadCss: async (url) => () => removed.push(url),
    failed: (pluginId, error) => failures.push([pluginId, error]),
  }, registry);

  await load([{ pluginId: "demo", entry: "demo.mjs", css: ["demo.css"] }]);

  assert.equal(registry.get("demo"), undefined);
  assert.deepEqual(removed, ["demo.css"]);
  assert.equal(failures.length, 1);
});

test("an entry whose identity does not match its admitted pluginId is refused", async () => {
  const registry = new PluginBackgroundRegistry();
  const failures: unknown[] = [];
  const load = createRuntimePluginBackgroundLoader({
    importModule: async () => ({ default: { pluginId: "other", setup: () => {} } }),
    loadCss: async () => () => {},
    failed: (pluginId, error) => failures.push([pluginId, error]),
  }, registry);

  await load([{ pluginId: "demo", entry: "demo.mjs", css: [] }]);

  assert.equal(registry.get("demo"), undefined);
  assert.equal(failures.length, 1);
});

test("is idempotent: an already-registered or already-reported plugin is never reconsidered", async () => {
  const registry = new PluginBackgroundRegistry();
  let imports = 0;
  const setup = () => {};
  const load = createRuntimePluginBackgroundLoader({
    importModule: async () => { imports += 1; return { default: { pluginId: "demo", setup } }; },
    loadCss: async () => () => {},
    failed: () => assert.fail("unexpected failure"),
  }, registry);
  const entry = { pluginId: "demo", entry: "demo.mjs", css: [] };

  assert.deepEqual(await load([entry]), ["demo"]);
  assert.deepEqual(await load([entry]), [], "second call must skip an already-registered plugin");
  assert.equal(imports, 1);

  const failLoad = createRuntimePluginBackgroundLoader({
    importModule: async () => { throw new Error("boom"); },
    loadCss: async () => () => {},
    failed: () => undefined,
  });
  const failing = { pluginId: "broken", entry: "broken.mjs", css: [] };
  assert.deepEqual(await failLoad([failing]), ["broken"]);
  assert.deepEqual(await failLoad([failing]), [], "an already-reported failure must not be retried within the session");
});
