import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import { wireRoleObservationBubbles } from "./roleBubble.js";

test("a role reply becomes a bubble only after observe_screen completed", () => {
  const bridge = new EventEmitter();
  const accepted: Array<{ roleId: string; reply: string }> = [];
  wireRoleObservationBubbles(bridge as never, {
    acceptRoleObservationReply: (roleId, reply) => accepted.push({ roleId, reply }),
  });

  bridge.emit("event", {
    method: "chat.done",
    payload: { role_id: "mira", reply: "我看到你在写代码。", tools_used: ["observe_screen"] },
  });
  bridge.emit("event", {
    method: "chat.done",
    payload: { role_id: "mira", reply: "普通回复不应显示气泡。", tools_used: [] },
  });

  assert.deepEqual(accepted, [{ roleId: "mira", reply: "我看到你在写代码。" }]);
});
