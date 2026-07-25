import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import { wireRoleReplyBubbles } from "./roleBubble.js";

test("desktop replies from the bound role become bubbles without using observe_screen", () => {
  const bridge = new EventEmitter();
  const accepted: Array<{ roleId: string; reply: string }> = [];
  wireRoleReplyBubbles(bridge as never, {
    acceptRoleReply: (roleId, reply) => accepted.push({ roleId, reply }),
  });

  bridge.emit("event", {
    method: "chat.done",
    payload: { role_id: "mira", reply: "我看到你在写代码。", tools_used: ["observe_screen"] },
  });
  bridge.emit("event", {
    method: "chat.done",
    payload: { role_id: "mira", reply: "普通回复不应显示气泡。", tools_used: [] },
  });

  assert.deepEqual(accepted, [
    { roleId: "mira", reply: "我看到你在写代码。" },
    { roleId: "mira", reply: "普通回复不应显示气泡。" },
  ]);
});
