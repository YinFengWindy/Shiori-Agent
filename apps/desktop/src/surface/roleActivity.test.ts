import assert from "node:assert/strict";
import test from "node:test";
import type { BridgeEvent } from "@shiori/sdk/contract";
import { surfaceRoleActivity } from "./roleActivity.js";

function event(method: string, payload: Record<string, unknown>): BridgeEvent {
  return { id: "event", type: "event", method, payload };
}

test("real chat delta/error envelopes resolve role identity from their session key", () => {
  assert.deepEqual(surfaceRoleActivity(event("chat.delta", { session_key: "role:mira", turn_id: "turn", delta: "hello" })), {
    roleId: "mira", sessionKey: "role:mira", phase: "running", notify: false,
  });
  assert.equal(surfaceRoleActivity(event("chat.error", { session_key: "role:mira", error: "failure" }))?.phase, "failed");
  assert.equal(surfaceRoleActivity(event("chat.done", { role_id: "mira", session_key: "role:mira", reply: "hello" }))?.phase, "review");
});

test("incremental and full session updates preserve proactive notification semantics", () => {
  const message = { role: "assistant", metadata: { proactive: true } };
  assert.deepEqual(surfaceRoleActivity(event("session.updated", { session: { key: "role:mira", metadata: {} }, message })), {
    roleId: "mira", sessionKey: "role:mira", phase: "waiting", notify: true,
  });
  assert.equal(surfaceRoleActivity(event("session.updated", { session: { key: "other-channel", metadata: { role_id: "mira" }, messages: [message] } }))?.notify, true);
  assert.equal(surfaceRoleActivity(event("session.updated", { session: { key: "role:mira", messages: [message] }, message: { role: "user" } }))?.phase, "review");
});

test("unknown events and envelopes without an attributable role/session are ignored", () => {
  for (const item of [event("chat.delta", {}), event("chat.delta", { session_key: "foreign" }), event("chat.delta", { session_key: "role:" }), event("plugin.example.changed", { role_id: "mira", session_key: "role:mira" })]) {
    assert.equal(surfaceRoleActivity(item), null);
  }
});
