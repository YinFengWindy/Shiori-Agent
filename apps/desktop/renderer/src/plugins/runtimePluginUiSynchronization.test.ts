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

test("a new activation of unchanged code is acknowledged again with this window's outcome (#857)", async () => {
  const reports: string[] = [];
  const sync = createRuntimePluginUiSynchronization({
    importModule: async (url) => {
      if (url === "broken") throw new Error("broken module");
      return { default: { pluginId: "demo" } };
    },
    loadCss: async () => () => undefined,
    register: () => undefined,
    unregister: () => undefined,
    succeeded: (entry) => { reports.push(`ok:${entry.pluginId}:${entry.activationToken}`); },
    failed: (entry, error) => { reports.push(`failed:${entry.pluginId}:${entry.activationToken}:${String(error)}`); },
  });
  const demo = { pluginId: "demo", entry: "demo", css: [], activationToken: "t1" };
  const broken = { pluginId: "other", entry: "broken", css: [], activationToken: "b1" };
  await sync([demo, broken]);
  // The backend reloaded "demo" (new token); "other" kept its activation.
  await sync([{ ...demo, activationToken: "t2" }, broken]);
  await sync([{ ...demo, activationToken: "t2" }, { ...broken, activationToken: "b2" }]);
  assert.deepEqual(reports, [
    "ok:demo:t1",
    "failed:other:b1:Error: broken module",
    "ok:demo:t2",
    "failed:other:b2:Error: broken module",
  ]);
});


test("runtime UI failures retain the RPC cause in their displayed diagnostic state", async () => {
  const { PluginBridgeError } = await import("@yinfengwindy/shiori-sdk");
  const sync = createRuntimePluginUiSynchronization({
    importModule: async () => { throw new PluginBridgeError("本地服务处理失败", "internal_error", { detail: "module asset missing token=private-value" }); },
    loadCss: async () => () => undefined, register: () => undefined, unregister: () => undefined, failed: () => undefined,
  });
  const failures = await sync([{ pluginId: "demo", entry: "demo", css: [] }]);
  assert.match(failures.get("demo") ?? "", /module asset missing/);
  assert.doesNotMatch(failures.get("demo") ?? "", /private-value/);
});
