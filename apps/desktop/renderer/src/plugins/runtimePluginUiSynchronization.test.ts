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
