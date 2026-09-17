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
  // #262: absent on the wire (a plugin with no declared renderer entries, or
  // one the backend has not yet started tracking) must default to empty,
  // never undefined — callers compare its length directly.
  assert.deepEqual(plugin.pendingRendererKinds, []);
});

it("surfaces pendingRendererKinds verbatim when the backend reports them (#262 AC1)", async () => {
  const client = createPluginBridgeClient(async ({ method }) => ({
    id: "1", type: "response", method, error: null, payload: { plugins: [{
      id: "demo", candidate_id: "workspace/demo", source: "workspace", directory: "C:/workspace/plugins/demo",
      name: "demo", version: "1.0.0", description: "", enabled: true, can_toggle: true,
      state: "ACTIVE", error: "", diagnostic: null, has_config_schema: false, supports_hot_unload: true,
      pending_renderer_kinds: ["background", "ui"],
    }] },
  }));
  const [plugin] = await client.listPlugins();
  assert.deepEqual(plugin.pendingRendererKinds, ["background", "ui"]);
});

describe("reportActivation (#262)", () => {
  it("sends a success report without a reason field", async () => {
    const calls: unknown[] = [];
    const client = createPluginBridgeClient(async (request) => {
      calls.push(request);
      return { id: "1", type: "response", method: request.method, error: null, payload: {} };
    });
    await client.reportActivation("demo", "ui", { ok: true, activationToken: "token-1" });
    assert.deepEqual(calls, [{
      method: "plugins.activation.report",
      payload: { plugin_id: "demo", kind: "ui", ok: true, activation_token: "token-1" },
    }]);
  });

  it("sends a failure report including its reason", async () => {
    const calls: unknown[] = [];
    const client = createPluginBridgeClient(async (request) => {
      calls.push(request);
      return { id: "1", type: "response", method: request.method, error: null, payload: {} };
    });
    await client.reportActivation("demo", "background", { ok: false, reason: "module threw", activationToken: "token-1" });
    assert.deepEqual(calls, [{
      method: "plugins.activation.report",
      payload: { plugin_id: "demo", kind: "background", ok: false, activation_token: "token-1", reason: "module threw" },
    }]);
  });
});

describe("createPluginRpcClient", () => {
  it("does not touch window.miraDesktop until a call is actually made", () => {
    // Building the client (as pluginUiModuleContract.tsx does once per
    // plugin at UI registration time) must not require window.miraDesktop
    // to exist yet; only invoking .call() should reach it.
    assert.doesNotThrow(() => createPluginRpcClient("demo"));
  });
});
