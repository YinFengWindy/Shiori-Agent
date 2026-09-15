import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createPluginBridgeClient, createPluginRpcClient } from "./pluginBridgeClient.js";

it("preserves candidate identity and structured admission diagnostics from the bridge", async () => {
  const diagnostic = { code: "duplicate_id", stage: "discovery", field: "id", reason: "conflict", path: "C:/workspace/plugins/demo", state: "CONFLICT" };
  const client = createPluginBridgeClient(async ({ method }) => ({
    id: "1", type: "response", method, error: null, payload: { plugins: [{
      id: "demo", candidate_id: "workspace/demo", source: "workspace", directory: "C:/workspace/plugins/demo",
      name: "demo", version: "1.0.0", description: "", enabled: true, can_toggle: false,
      state: "CONFLICT", error: "conflict", diagnostic, has_config_schema: false, supports_hot_unload: true,
    }] },
  }));
  const [plugin] = await client.listPlugins();
  assert.equal(plugin.candidateId, "workspace/demo");
  assert.equal(plugin.source, "workspace");
  assert.equal(plugin.directory, "C:/workspace/plugins/demo");
  assert.equal(plugin.canToggle, false);
  assert.deepEqual(plugin.diagnostic, diagnostic);
});

describe("createPluginRpcClient", () => {
  it("prefixes every call with the owning plugin's own plugin.<id>.* namespace", async () => {
    const calls: string[] = [];
    const invoke = async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
      calls.push(method);
      return { id: "1", type: "response" as const, method, error: null, payload: { echoed: payload } };
    };

    const client = createPluginRpcClient("demo", invoke);
    await client.call("doThing", { x: 1 });
    await client.call("other");

    // The plugin only ever supplies the bare method name; the client — not
    // the caller — owns constructing the full "plugin.<id>.<method>" name,
    // so there is no way for injected client code to address another
    // plugin's namespace or a bare top-level bridge method.
    assert.deepEqual(calls, ["plugin.demo.doThing", "plugin.demo.other"]);
  });

  it("does not touch window.miraDesktop until a call is actually made", () => {
    // Building the client (as pluginUiModuleContract.tsx does once per
    // plugin at UI registration time) must not require window.miraDesktop
    // to exist yet; only invoking .call() should reach it.
    assert.doesNotThrow(() => createPluginRpcClient("demo"));
  });
});
