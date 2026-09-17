import assert from "node:assert/strict";
import { test } from "node:test";
import { loadRuntimePluginUi } from "./runtimePluginUi";

test("ESM or CSS failure cleans only its plugin and preserves the original diagnostic", async () => {
  const failure = new SyntaxError("bad plugin syntax");
  const events: unknown[] = [];
  const dispose = await loadRuntimePluginUi([
    { pluginId: "bad", entry: "bad", css: ["bad.css"] },
    { pluginId: "good", entry: "good", css: ["good.css"] },
  ], {
    importModule: async (entry) => { if (entry === "bad") throw failure; return { default: { pluginId: "good" } }; },
    loadCss: async (url) => () => { events.push(`remove ${url}`); },
    register: (module) => { events.push(`register ${module.pluginId}`); },
    unregister: (id) => { events.push(`unregister ${id}`); },
    failed: (_entry, error) => { events.push(error); },
  });
  assert.deepEqual(events, ["unregister bad", "remove bad.css", failure, "register good"]);
  dispose();
  assert.deepEqual(events.slice(-2), ["unregister good", "remove good.css"]);
});

test("reports the admitted entry through succeeded once it registers (#262)", async () => {
  const succeeded: unknown[] = [];
  await loadRuntimePluginUi([{ pluginId: "demo", entry: "demo", css: [], activationToken: "token-1" }], {
    importModule: async () => ({ default: { pluginId: "demo" } }),
    loadCss: async () => () => undefined,
    register: () => undefined,
    unregister: () => undefined,
    succeeded: (entry) => succeeded.push(entry),
    failed: () => assert.fail("unexpected failure"),
  });
  assert.deepEqual(succeeded, [{ pluginId: "demo", entry: "demo", css: [], activationToken: "token-1" }]);
});

test("stylesheet failure removes earlier styles and never evaluates the plugin", async () => {
  const removed: string[] = [];
  const failure = new Error("missing stylesheet");
  let diagnostic: unknown;
  await loadRuntimePluginUi([{ pluginId: "demo", entry: "demo", css: ["first", "missing"] }], {
    importModule: async () => assert.fail("failed CSS must prevent module evaluation"),
    loadCss: async (url) => { if (url === "missing") throw failure; return () => { removed.push(url); }; },
    register: () => assert.fail("failed plugin must not register"),
    unregister: () => undefined,
    failed: (_entry, error) => { diagnostic = error; },
  });
  assert.deepEqual(removed, ["first"]);
  assert.equal(diagnostic, failure);
});
