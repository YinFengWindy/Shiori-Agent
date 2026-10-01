import assert from "node:assert/strict";
import { test } from "node:test";
import type { BridgeEvent } from "@shiori/plugin-sdk/contract";
import { notificationMessages } from "./message.js";

function event(payload: Record<string, unknown> = {}): BridgeEvent {
  return {
    id: "request-1", type: "event", method: "session.updated",
    payload: {
      change: "message_appended",
      session: { key: "role:mira", metadata: { role_name: "米拉" } },
      message: { id: "reply-1", role: "assistant", content: "**晚安**\n做个好梦" },
      ...payload,
    },
  };
}

test("normal replies and proactive commits use the role's name and a plain preview", () => {
  for (const id of ["request-1", "proactive", "proactive:mira"]) {
    const messages = notificationMessages({ ...event(), id });
    assert.equal(messages.length, 1);
    assert.deepEqual(messages[0], {
      key: "role:mira:reply-1", roleId: "mira", title: "米拉", body: "晚安 做个好梦",
    });
  }
});

test("only changed committed assistant rows can alert", () => {
  for (const role of ["user", "tool", "system", "error"]) {
    assert.deepEqual(notificationMessages(event({ message: { id: "1", role, content: "hello" } })), []);
  }
  for (const message of [
    { role: "assistant", content: "uncommitted" },
    { id: "1", role: "assistant", content: "partial", streaming: true },
    { id: "1", role: "assistant", content: "", reasoning_content: "secret thought" },
    { id: "1", role: "assistant", content: "", tool_chain: [{ text: "tool" }] },
    { id: "1", role: "assistant", content: "remote", metadata: { message_source: { channel: "qq" } } },
    { id: "1", role: "assistant", content: "remote", metadata: { transport_channel: "qq" } },
  ]) assert.deepEqual(notificationMessages(event({ message })), []);
});

test("history, streams, metadata changes and other-channel summaries never notify", () => {
  assert.deepEqual(notificationMessages({ ...event(), method: "chat.delta" }), []);
  assert.deepEqual(notificationMessages({ ...event(), method: "chat.done" }), []);
  assert.deepEqual(notificationMessages(event({ change: "metadata_updated" })), []);
  assert.deepEqual(notificationMessages(event({ change: undefined })), []);
  assert.deepEqual(notificationMessages(event({ session: { key: "qq:123", metadata: {} } })), []);
  assert.deepEqual(notificationMessages(event({ message: null, messages: [] })), []);
  assert.deepEqual(notificationMessages(event({
    message: null,
    session: { key: "role:mira", messages: [event().payload.message] },
  })), []);
});

test("media-only replies get a placeholder and emoji previews are capped without splitting code points", () => {
  assert.equal(notificationMessages(event({
    message: { seq: 3, role: "assistant", content: "", media: ["cat.png"] },
  }))[0]?.body, "[图片]");
  assert.equal(notificationMessages(event({
    message: { id: "long", role: "assistant", content: "🌙".repeat(180) },
  }))[0]?.body, `${"🌙".repeat(159)}…`);
});

test("changed-message batches include each new assistant and missing names use the role id", () => {
  const messages = notificationMessages(event({
    session: { key: "role:mira" }, message: null,
    messages: [
      { id: "user", role: "user", content: "hello" },
      { id: "first", role: "assistant", content: "hello" },
      { seq: 4, role: "assistant", content: "again" },
    ],
  }));
  assert.deepEqual(messages.map(({ key, title }) => ({ key, title })), [
    { key: "role:mira:first", title: "mira" },
    { key: "role:mira:seq:4", title: "mira" },
  ]);
});
