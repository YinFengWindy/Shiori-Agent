import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { reportRuntimePluginActivation, reportRuntimePluginRendererLoadFailure } from "./runtimePluginActivationReporting";

afterEach(() => {
  Reflect.deleteProperty(globalThis, "window");
});

test("reports a success outcome carrying the entry's activation token", async () => {
  const calls: unknown[] = [];
  const pluginBridge = { reportActivation: async (pluginId: string, kind: string, outcome: unknown) => { calls.push({ pluginId, kind, outcome }); } };
  reportRuntimePluginActivation(pluginBridge, { pluginId: "demo", activationToken: "token-1" }, "ui", { ok: true });
  await Promise.resolve();
  assert.deepEqual(calls, [{ pluginId: "demo", kind: "ui", outcome: { ok: true, activationToken: "token-1" } }]);
});

test("reports a failure outcome carrying its reason and the activation token", async () => {
  const calls: unknown[] = [];
  const pluginBridge = { reportActivation: async (pluginId: string, kind: string, outcome: unknown) => { calls.push({ pluginId, kind, outcome }); } };
  reportRuntimePluginActivation(pluginBridge, { pluginId: "demo", activationToken: "token-1" }, "background", { ok: false, reason: "boom" });
  await Promise.resolve();
  assert.deepEqual(calls, [{ pluginId: "demo", kind: "background", outcome: { ok: false, reason: "boom", activationToken: "token-1" } }]);
});

test("defaults a missing activation token to an empty string rather than throwing", async () => {
  const calls: unknown[] = [];
  const pluginBridge = { reportActivation: async (_pluginId: string, _kind: string, outcome: unknown) => { calls.push(outcome); } };
  reportRuntimePluginActivation(pluginBridge, { pluginId: "demo" }, "surface", { ok: true });
  await Promise.resolve();
  assert.deepEqual(calls, [{ ok: true, activationToken: "" }]);
});

test("surfaces a transport failure through the renderer diagnostic channel instead of swallowing it", async () => {
  const diagnostics: unknown[] = [];
  (globalThis as { window?: unknown }).window = { miraDesktop: { reportRendererDiagnostic: (payload: unknown) => diagnostics.push(payload) } };
  const pluginBridge = { reportActivation: async () => { throw new Error("bridge down"); } };
  reportRuntimePluginActivation(pluginBridge, { pluginId: "demo", activationToken: "token-1" }, "ui", { ok: true });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(diagnostics.length, 1);
  const [diagnostic] = diagnostics as [{ kind: string; message: string; details: Record<string, unknown> }];
  assert.equal(diagnostic.kind, "error");
  assert.match(diagnostic.message, /bridge down/);
  assert.deepEqual(diagnostic.details, { pluginId: "demo", event: "plugin-ui.activation-report-failed", stage: "renderer" });
});

test("a normal changed:false response is not itself treated as a transport failure", async () => {
  const diagnostics: unknown[] = [];
  (globalThis as { window?: unknown }).window = { miraDesktop: { reportRendererDiagnostic: (payload: unknown) => diagnostics.push(payload) } };
  const pluginBridge = { reportActivation: async () => undefined };
  reportRuntimePluginActivation(pluginBridge, { pluginId: "demo", activationToken: "stale" }, "ui", { ok: false, reason: "stale" });
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(diagnostics, []);
});

test("reportRuntimePluginRendererLoadFailure reports the load diagnostic, then the activation failure", async () => {
  const diagnostics: unknown[] = [];
  const activationCalls: unknown[] = [];
  (globalThis as { window?: unknown }).window = { miraDesktop: { reportRendererDiagnostic: (payload: unknown) => diagnostics.push(payload) } };
  const pluginBridge = { reportActivation: async (pluginId: string, kind: string, outcome: unknown) => { activationCalls.push({ pluginId, kind, outcome }); } };
  reportRuntimePluginRendererLoadFailure(
    pluginBridge,
    "plugin-ui.load.failed",
    { pluginId: "demo", activationToken: "token-1" },
    "ui",
    new Error("module threw"),
  );
  await Promise.resolve();
  assert.deepEqual(diagnostics, [{
    kind: "error", message: "module threw",
    details: { pluginId: "demo", event: "plugin-ui.load.failed", state: "FAILED", stage: "renderer" },
  }]);
  assert.deepEqual(activationCalls, [{
    pluginId: "demo", kind: "ui",
    outcome: { ok: false, reason: "module threw", activationToken: "token-1" },
  }]);
});
