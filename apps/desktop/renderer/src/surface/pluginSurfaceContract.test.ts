import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import type { PluginSurfaceModule } from "@yinfengwindy/shiori-sdk";
import { applyPluginSurfaceModules } from "./pluginSurfaceContract";
import { PluginSurfaceRegistry } from "./pluginSurfaceRegistry";

const component = () => null;

/**
 * Silences the module's own diagnostics while asserting they happened, so a
 * skipped module is proven to be *reported* rather than dropped in silence —
 * a surface window that fails to mount is an invisible transparent rectangle
 * with nothing to click.
 */
let errors: unknown[][] = [];
let warnings: unknown[][] = [];
const realError = console.error;
const realWarn = console.warn;

beforeEach(() => {
  errors = [];
  warnings = [];
  console.error = (...args: unknown[]) => { errors.push(args); };
  console.warn = (...args: unknown[]) => { warnings.push(args); };
});

afterEach(() => {
  console.error = realError;
  console.warn = realWarn;
});

test("registers a well-formed surface module under its plugin id", () => {
  const registry = new PluginSurfaceRegistry();
  applyPluginSurfaceModules(
    { "/plugins/demo/surface/index.tsx": { default: { pluginId: "demo", surface: { component } } } },
    registry,
  );
  assert.deepEqual(registry.get("demo"), { slot: "desktop.surface", pluginId: "demo", Component: component });
  assert.deepEqual(errors, []);
});

test("a malformed module is reported and skipped, and never blocks a valid one", () => {
  const registry = new PluginSurfaceRegistry();
  applyPluginSurfaceModules(
    {
      "/plugins/a/surface/index.tsx": { default: null as unknown as PluginSurfaceModule },
      "/plugins/b/surface/index.tsx": { default: { surface: { component } } as unknown as PluginSurfaceModule },
      "/plugins/c/surface/index.tsx": { default: { pluginId: "c" } as unknown as PluginSurfaceModule },
      "/plugins/d/surface/index.tsx": {
        default: { pluginId: "d", surface: { component: "nope" } } as unknown as PluginSurfaceModule,
      },
      "/plugins/good/surface/index.tsx": { default: { pluginId: "good", surface: { component } } },
    },
    registry,
  );
  assert.deepEqual(registry.list().map((entry) => entry.pluginId), ["good"]);
  assert.equal(errors.length, 4, "every skipped module must say so");
});

test("a duplicate plugin id is warned about rather than silently replacing the first", () => {
  const registry = new PluginSurfaceRegistry();
  const second = () => null;
  applyPluginSurfaceModules(
    { "/plugins/demo/surface/index.tsx": { default: { pluginId: "demo", surface: { component } } } },
    registry,
  );
  applyPluginSurfaceModules(
    { "/plugins/demo/surface/index.tsx": { default: { pluginId: "demo", surface: { component: second } } } },
    registry,
  );
  assert.equal(registry.get("demo")?.Component, component);
  assert.equal(warnings.length, 1);
});

test("unregistering a plugin removes its surface", () => {
  const registry = new PluginSurfaceRegistry();
  applyPluginSurfaceModules(
    { "/plugins/demo/surface/index.tsx": { default: { pluginId: "demo", surface: { component } } } },
    registry,
  );
  registry.unregister("demo");
  assert.equal(registry.get("demo"), undefined);
  assert.deepEqual(registry.list(), []);
});
