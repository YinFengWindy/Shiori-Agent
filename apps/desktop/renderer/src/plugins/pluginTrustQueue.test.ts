import assert from "node:assert/strict";
import { test } from "node:test";
import type { PluginSummary } from "./pluginBridgeClient";
import { PluginTrustQueue } from "./pluginTrustQueue";

function plugin(id: string, overrides: Partial<PluginSummary> = {}): PluginSummary {
  return {
    id, candidateId: `workspace/${id}`, source: "workspace", directory: `workspace/${id}`,
    name: id, version: "1", description: "", enabled: true, canToggle: false,
    state: "UNTRUSTED", error: "", diagnostic: null, hasConfigSchema: false,
    capabilities: [], channels: [], category: "feature", supportsHotUnload: true,
    pendingRendererKinds: [], canTrust: true, trustFingerprint: "first", contentFingerprint: "first",
    ...overrides,
  };
}

function storage() {
  const values = new Map<string, string>();
  return { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => { values.set(key, value); } };
}

test("startup queues enabled trustable content and cancellation survives renderer and bridge refreshes", () => {
  const persisted = storage();
  const queue = new PluginTrustQueue();
  const disabled = plugin("disabled", { enabled: false });
  const invalid = plugin("invalid", { canTrust: false, state: "BLOCKED" });
  const trusted = plugin("trusted", { canTrust: false, state: "ACTIVE" });
  const first = plugin("one");
  const second = plugin("two");
  const rows = [disabled, invalid, trusted, first, second];
  queue.synchronize(rows);
  assert.equal(queue.getSnapshot().request, null);
  queue.initialize("app-one", persisted);
  assert.equal(queue.getSnapshot().request?.plugin.id, "one");
  const shown = queue.getSnapshot();
  queue.synchronize([...rows]);
  assert.equal(queue.getSnapshot(), shown, "unchanged snapshot keeps reference identity");
  queue.dismiss();
  assert.equal(queue.getSnapshot().request?.plugin.id, "two");
  queue.dismiss();
  queue.synchronize(rows);
  assert.equal(queue.getSnapshot().request, null);
  const reconnected = new PluginTrustQueue();
  reconnected.synchronize(rows);
  reconnected.initialize("app-one", persisted);
  assert.equal(reconnected.getSnapshot().request, null);
  reconnected.request(first);
  assert.equal(reconnected.getSnapshot().request?.plugin.id, "one", "manual retry stays available");
  reconnected.dismiss();
  const restarted = new PluginTrustQueue();
  restarted.synchronize(rows);
  restarted.initialize("app-two", persisted);
  assert.equal(restarted.getSnapshot().request?.plugin.id, "one");
});

test("displayed bytes stay fixed, changed content disables confirmation, and the new bytes require a new prompt", () => {
  const queue = new PluginTrustQueue();
  const original = plugin("one");
  queue.initialize("app-one", storage());
  queue.synchronize([original]);
  queue.synchronize([plugin("one", { trustFingerprint: "changed", contentFingerprint: "changed" })]);
  assert.equal(queue.getSnapshot().request?.plugin.trustFingerprint, "first");
  assert.equal(queue.getSnapshot().stale, true);
  assert.equal(queue.begin(), null);
  queue.dismiss();
  assert.equal(queue.getSnapshot().request?.plugin.trustFingerprint, "changed");
  assert.equal(queue.getSnapshot().stale, false);
});

test("explicit enable and trust-only stay distinct; busy retries keep one operation identity", () => {
  const queue = new PluginTrustQueue();
  const disabled = plugin("manual", { enabled: false });
  queue.synchronize([disabled]);
  queue.request(disabled);
  assert.equal(queue.getSnapshot().request?.enable, false);
  queue.dismiss();
  queue.request(disabled, true);
  const request = queue.begin();
  assert.equal(request?.enable, true);
  queue.dismiss();
  assert.equal(queue.getSnapshot().request, request);
  assert.equal(queue.begin(), null);
  queue.fail("response lost");
  assert.equal(queue.begin()?.operationId, request?.operationId);
  queue.synchronize([plugin("manual", { enabled: true, canTrust: false, trusted: true, state: "ACTIVE", trustFingerprint: null })]);
  queue.complete();
  assert.equal(queue.getSnapshot().request, null);
});

test("a matching fingerprint with a conflict is not an acknowledged trust grant", () => {
  const queue = new PluginTrustQueue();
  queue.initialize("app-one", storage());
  queue.synchronize([plugin("one")]);
  queue.synchronize([plugin("one", { state: "CONFLICT", canTrust: false, trusted: false })]);
  assert.equal(queue.getSnapshot().request?.plugin.id, "one");
  assert.equal(queue.getSnapshot().stale, true);
  assert.equal(queue.begin(), null);
});
