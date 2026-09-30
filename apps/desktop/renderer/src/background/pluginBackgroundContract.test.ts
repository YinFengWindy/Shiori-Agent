import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";
import type { PluginBackgroundContribution } from "@shiori/plugin-sdk";
import { applyPluginBackgroundModules } from "./pluginBackgroundContract";
import { PluginBackgroundRegistry } from "./pluginBackgroundRegistry";

const setup = () => {};

/**
 * Silences the module's own diagnostics while asserting they happened —
 * mirrors `pluginSurfaceContract.test.ts`. A skipped background module has no
 * on-screen failure of its own (there is no DOM here at all), so proving it
 * is *reported* rather than dropped in silence matters even more than for a
 * surface.
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

test("registers a well-formed background module under its plugin id", () => {
  const registry = new PluginBackgroundRegistry();
  applyPluginBackgroundModules(
    { "/plugins/demo/background/index.ts": { default: { pluginId: "demo", setup } } },
    registry,
  );
  assert.deepEqual(registry.get("demo"), { slot: "app.background", pluginId: "demo", setup });
  assert.deepEqual(errors, []);
});

test("a malformed module is reported and skipped, and never blocks a valid one", () => {
  const registry = new PluginBackgroundRegistry();
  applyPluginBackgroundModules(
    {
      "/plugins/a/background/index.ts": { default: null as unknown as PluginBackgroundContribution },
      "/plugins/b/background/index.ts": { default: { setup } as unknown as PluginBackgroundContribution },
      "/plugins/c/background/index.ts": { default: { pluginId: "c" } as unknown as PluginBackgroundContribution },
      "/plugins/d/background/index.ts": {
        default: { pluginId: "d", setup: "nope" } as unknown as PluginBackgroundContribution,
      },
      "/plugins/good/background/index.ts": { default: { pluginId: "good", setup } },
    },
    registry,
  );
  assert.deepEqual(registry.list().map((entry) => entry.pluginId), ["good"]);
  assert.equal(errors.length, 4, "every skipped module must say so");
});

test("a duplicate plugin id is warned about rather than silently replacing the first", () => {
  const registry = new PluginBackgroundRegistry();
  const secondSetup = () => {};
  applyPluginBackgroundModules(
    { "/plugins/demo/background/index.ts": { default: { pluginId: "demo", setup } } },
    registry,
  );
  applyPluginBackgroundModules(
    { "/plugins/demo/background/index.ts": { default: { pluginId: "demo", setup: secondSetup } } },
    registry,
  );
  assert.equal(registry.get("demo")?.setup, setup);
  assert.equal(warnings.length, 1);
});

test("unregistering a plugin removes its background entry", () => {
  const registry = new PluginBackgroundRegistry();
  applyPluginBackgroundModules(
    { "/plugins/demo/background/index.ts": { default: { pluginId: "demo", setup } } },
    registry,
  );
  registry.unregister("demo");
  assert.equal(registry.get("demo"), undefined);
  assert.deepEqual(registry.list(), []);
});
