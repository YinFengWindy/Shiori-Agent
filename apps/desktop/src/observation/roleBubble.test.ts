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

test("proactive session updates expose the new assistant message as a bubble", () => {
  const bridge = new EventEmitter();
  const accepted: Array<{ roleId: string; reply: string }> = [];
  wireRoleReplyBubbles(bridge as never, {
    acceptRoleReply: (roleId, reply) => accepted.push({ roleId, reply }),
  });

  bridge.emit("event", {
    id: "proactive",
    method: "session.updated",
    payload: {
      session: {
        metadata: { role_id: "mira" },
        messages: [
          { role: "assistant", content: "主动来找你了。", metadata: { proactive: true } },
        ],
      },
    },
  });

  assert.deepEqual(accepted, [{ roleId: "mira", reply: "主动来找你了。" }]);
});

test("incremental proactive updates read the changed message without a full session snapshot", () => {
  const bridge = new EventEmitter();
  const accepted: Array<{ roleId: string; reply: string }> = [];
  wireRoleReplyBubbles(bridge as never, {
    acceptRoleReply: (roleId, reply) => accepted.push({ roleId, reply }),
  });

  bridge.emit("event", {
    id: "proactive",
    method: "session.updated",
    payload: {
      role_id: "mira",
      session: {
        key: "role:mira",
        metadata: {},
      },
      change: "message_appended",
      message: {
        id: "role:mira:9",
        role: "assistant",
        content: "增量主动消息。",
        metadata: { proactive: true },
      },
    },
  });

  assert.deepEqual(accepted, [{ roleId: "mira", reply: "增量主动消息。" }]);
});

test("ordinary session updates and stale proactive snapshots do not create bubbles", () => {
  const bridge = new EventEmitter();
  const accepted: Array<{ roleId: string; reply: string }> = [];
  wireRoleReplyBubbles(bridge as never, {
    acceptRoleReply: (roleId, reply) => accepted.push({ roleId, reply }),
  });

  bridge.emit("event", {
    id: "session.open",
    method: "session.updated",
    payload: {
      session: {
        metadata: { role_id: "mira" },
        messages: [{ role: "assistant", content: "旧主动消息", proactive: true }],
      },
    },
  });
  bridge.emit("event", {
    id: "proactive",
    method: "session.updated",
    payload: {
      session: {
        metadata: { role_id: "mira" },
        messages: [{ role: "assistant", content: "普通刷新", metadata: {} }],
      },
    },
  });

  assert.deepEqual(accepted, []);
});
