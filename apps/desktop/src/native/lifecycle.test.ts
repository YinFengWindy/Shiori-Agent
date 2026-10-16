import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { test } from "node:test";
import { bindNativeDocumentLifecycle, revokeNativeSessionsOnBridgeEvent } from "./lifecycle";

test("actual document reload, crash and destruction release resources; frames and same-document navigation do not", () => {
  const source = new EventEmitter(); let released = 0;
  bindNativeDocumentLifecycle(source, () => { released++; });
  source.emit("did-start-navigation", { isMainFrame: false, isSameDocument: false });
  source.emit("did-start-navigation", { isMainFrame: true, isSameDocument: true });
  assert.equal(released, 0);
  source.emit("did-start-navigation", { isMainFrame: true, isSameDocument: false });
  source.emit("render-process-gone"); source.emit("destroyed");
  assert.equal(released, 3);
});

test("a runtime publication or exit revokes every native session; a plugin reload only its own (#857)", () => {
  const revoked: (string | undefined)[] = [];
  const revoke = (pluginId?: string) => { revoked.push(pluginId); };
  const event = (method: string, payload: Record<string, unknown> = {}) => ({ id: "event", type: "event" as const, method, payload });
  revokeNativeSessionsOnBridgeEvent(event("runtime.applied", { changed: false }), revoke);
  revokeNativeSessionsOnBridgeEvent(event("plugins.changed", { plugin_id: "pet" }), revoke);
  assert.deepEqual(revoked, []);
  revokeNativeSessionsOnBridgeEvent(event("plugins.reloaded", { plugin_ids: ["novelai", "story"] }), revoke);
  assert.deepEqual(revoked, ["novelai", "story"]);
  revokeNativeSessionsOnBridgeEvent(event("runtime.applied", { changed: true }), revoke);
  revokeNativeSessionsOnBridgeEvent(event("bridge.exit"), revoke);
  assert.deepEqual(revoked, ["novelai", "story", undefined, undefined]);
});
