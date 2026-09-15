import assert from "node:assert/strict";
import test from "node:test";
import type { BridgeEvent } from "../../../apps/desktop/src/bridge/shared";
import { readRoleReply } from "./roleReply";

function event(method: string, payload: Record<string, unknown>, id = "proactive"): BridgeEvent {
  return { id, type: "event", method, payload };
}

test("ordinary replies are independent of screen tool use", () => {
  for (const tools_used of [[], ["observe_screen"]]) {
    assert.deepEqual(readRoleReply(event("chat.done", { role_id: "mira", reply: "你好", tools_used })), { roleId: "mira", text: "你好" });
  }
  assert.equal(readRoleReply(event("chat.done", { role_id: "mira", reply: " " })), null);
});

test("incremental and snapshot proactive events retain role and producer filtering", () => {
  const message = { role: "assistant", content: "来找你啦", metadata: { proactive: true } };
  assert.deepEqual(readRoleReply(event("session.updated", { role_id: "mira", message })), { roleId: "mira", text: "来找你啦" });
  const payload = { session: { metadata: { role_id: "mira" }, messages: [message] } };
  assert.deepEqual(readRoleReply(event("session.updated", payload)), { roleId: "mira", text: "来找你啦" });
  assert.equal(readRoleReply(event("session.updated", payload, "session.open")), null);
  assert.equal(readRoleReply(event("session.updated", { role_id: "mira", message: { ...message, metadata: {} } })), null);
  assert.equal(readRoleReply(event("session.updated", { role_id: "mira", message: { ...message, role: "user" } })), null);
});
