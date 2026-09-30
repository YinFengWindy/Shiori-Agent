import assert from "node:assert/strict";
import { test } from "node:test";
import type { BridgeEvent } from "@shiori/plugin-sdk";
import { phoneConversationUpdateOf } from "./phonePayloads";

const event = (method: string, payload: Record<string, unknown>): BridgeEvent => ({ id: "e", type: "event", method, payload });

const payload = {
  role_id: "mira",
  thread_id: "t",
  conversation: {
    thread_id: "t", account_id: null, channel: "qq", chat_type: "group", display_name: "摸鱼群", is_user_chat: false,
    last_message: { role: "assistant", content: "我来", timestamp: "2026-09-29T10:00:00+08:00", has_media: false, sender_name: null },
  },
  messages: [{
    id: "m", seq: null, sender: "role", sender_id: null, sender_name: null, sender_is_user: false,
    content: "我来", media: [], timestamp: "2026-09-29T10:00:00+08:00",
  }],
};

test("a live update is read into the renderer's shape; other events are not updates", () => {
  const update = phoneConversationUpdateOf(event("phone.conversation.updated", payload));
  assert.equal(update?.conversation.displayName, "摸鱼群");
  assert.deepEqual(update?.messages.map((message) => [message.sender, message.content]), [["role", "我来"]]);
  assert.equal(phoneConversationUpdateOf(event("session.updated", payload)), null);
});

test("a live update that breaks the bridge contract fails loudly", () => {
  assert.throws(
    () => phoneConversationUpdateOf(event("phone.conversation.updated", { ...payload, messages: [{ id: 1 }] })),
    /负载格式不符/,
  );
});
