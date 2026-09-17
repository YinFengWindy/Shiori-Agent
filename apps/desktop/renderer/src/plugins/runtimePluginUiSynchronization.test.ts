import assert from "node:assert/strict";
import { test } from "node:test";
import { createRuntimePluginUiSynchronization } from "./runtimePluginUiSynchronization";

test("unchanged roster does not reevaluate UI; disable removes CSS and reenable registers again", async () => {
  const entry = { pluginId: "demo", entry: "demo", css: ["demo.css"] };
  const events: string[] = [];
  const sync = createRuntimePluginUiSynchronization({
    importModule: async () => { events.push("import"); return { default: { pluginId: "demo" } }; },
    loadCss: async () => { events.push("css"); return () => { events.push("remove css"); }; },
    register: () => { events.push("register"); },
    unregister: () => { events.push("unregister"); },
    failed: () => assert.fail("unexpected failure"),
  });
  await Promise.all([sync([entry]), sync([entry])]);
  assert.deepEqual(events, ["css", "import", "register"]);
  await sync([]);
  assert.deepEqual(events.slice(-2), ["unregister", "remove css"]);
  await sync([entry]);
  assert.deepEqual(events.slice(-3), ["css", "import", "register"]);
});

test("a changed activationToken alone does not reevaluate an otherwise-unchanged UI (#262)", async () => {
  // Every generation swap mints a fresh activationToken (#262), including
  // for a plugin whose UI package did not change at all. Reloading it on
  // every unrelated settings apply would be a real regression the identity
  // diff must not reintroduce.
  const events: string[] = [];
  const sync = createRuntimePluginUiSynchronization({
    importModule: async () => { events.push("import"); return { default: { pluginId: "demo" } }; },
    loadCss: async () => { events.push("css"); return () => { events.push("remove css"); }; },
    register: () => { events.push("register"); },
    unregister: () => { events.push("unregister"); },
    failed: () => assert.fail("unexpected failure"),
  });
  await sync([{ pluginId: "demo", entry: "demo", css: ["demo.css"], activationToken: "token-1" }]);
  assert.deepEqual(events, ["css", "import", "register"]);
  await sync([{ pluginId: "demo", entry: "demo", css: ["demo.css"], activationToken: "token-2" }]);
  assert.deepEqual(events, ["css", "import", "register"], "a token-only change must not dispose or reimport");
});
