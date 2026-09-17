import assert from "node:assert/strict";
import { test } from "node:test";
import { loadRuntimePluginSurface } from "./runtimePluginSurface";
import { PluginSurfaceRegistry } from "./pluginSurfaceRegistry";

const Component = () => null;

test("registers a well-formed external surface entry into the shared registry", async () => {
  const registry = new PluginSurfaceRegistry();
  const events: string[] = [];
  await loadRuntimePluginSurface(
    { pluginId: "demo", entry: "demo.mjs", css: ["demo.css"] },
    {
      importModule: async () => { events.push("import"); return { default: { pluginId: "demo", surface: { component: Component } } }; },
      loadCss: async (url) => { events.push(`css ${url}`); return () => events.push(`remove ${url}`); },
      failed: () => assert.fail("unexpected failure"),
    },
    registry,
  );
  assert.deepEqual(events, ["css demo.css", "import"]);
  assert.deepEqual(registry.get("demo"), { slot: "desktop.surface", pluginId: "demo", Component });
});

test("a declared entry's own error is reported and never imported or registered", async () => {
  const registry = new PluginSurfaceRegistry();
  const failures: unknown[] = [];
  await loadRuntimePluginSurface(
    { pluginId: "demo", entry: "demo.mjs", css: [], error: "package changed" },
    {
      importModule: async () => assert.fail("a declared-invalid entry must not be imported"),
      loadCss: async () => assert.fail("a declared-invalid entry must not load CSS"),
      failed: (pluginId, error) => failures.push([pluginId, error]),
    },
    registry,
  );
  assert.equal(registry.get("demo"), undefined);
  assert.equal(failures.length, 1);
});

test("a malformed module removes its loaded CSS and is reported, not registered", async () => {
  const registry = new PluginSurfaceRegistry();
  const removed: string[] = [];
  const failures: unknown[] = [];
  await loadRuntimePluginSurface(
    { pluginId: "demo", entry: "demo.mjs", css: ["demo.css"] },
    {
      importModule: async () => ({ default: { pluginId: "demo" /* no surface.component */ } }),
      loadCss: async (url) => () => removed.push(url),
      failed: (pluginId, error) => failures.push([pluginId, error]),
    },
    registry,
  );
  assert.equal(registry.get("demo"), undefined);
  assert.deepEqual(removed, ["demo.css"]);
  assert.equal(failures.length, 1);
});

test("an entry whose identity does not match its admitted pluginId is refused", async () => {
  const registry = new PluginSurfaceRegistry();
  const failures: unknown[] = [];
  await loadRuntimePluginSurface(
    { pluginId: "demo", entry: "demo.mjs", css: [] },
    {
      importModule: async () => ({ default: { pluginId: "other", surface: { component: Component } } }),
      loadCss: async () => () => {},
      failed: (pluginId, error) => failures.push([pluginId, error]),
    },
    registry,
  );
  assert.equal(registry.get("demo"), undefined);
  assert.equal(failures.length, 1);
});
