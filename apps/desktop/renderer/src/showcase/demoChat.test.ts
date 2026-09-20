/// <reference types="node" />
import assert from "node:assert/strict";
import { test } from "node:test";
import { createDemoChat } from "./demoChat";
import { chatSamples } from "./demoContent";

function storage() {
  let value: string | null = null;
  return { getItem: () => value, setItem: (_key: string, next: string) => { value = next; }, removeItem: () => { value = null; } };
}

test("free text records the input but plays the declared fixed sample, then restores history", async () => {
  const saved = storage();
  const chat = createDemoChat(saved, async () => undefined);
  await chat.send({ content: "完全不同的输入", attachments: [], replyTarget: null });
  assert.equal(chat.getSnapshot().messages.at(-2)?.content, "完全不同的输入");
  assert.equal(chat.getSnapshot().messages.at(-1)?.content, chatSamples[0].text);
  assert.equal(chat.getSnapshot().mood, chatSamples[0].mood);
  assert.equal(createDemoChat(saved).getSnapshot().messages.at(-1)?.content, chatSamples[0].text);
});

test("stop interrupts streaming and ignores late chunks without losing the user's message", async () => {
  let release: () => void = () => undefined;
  const saved = storage();
  const chat = createDemoChat(saved, () => new Promise<void>((resolve) => { release = resolve; }));
  const pending = chat.send({ content: "你好", attachments: [], replyTarget: null });
  assert.equal(chat.getSnapshot().sending, true);
  assert.equal(await chat.send({ content: "重复", attachments: [], replyTarget: null }), false);
  chat.cancel();
  release();
  await pending;
  assert.equal(chat.getSnapshot().sending, false);
  assert.equal(chat.getSnapshot().messages.at(-2)?.content, "你好");
  assert.equal(chat.getSnapshot().messages.at(-1)?.content, "");
  assert.equal(createDemoChat(saved).getSnapshot().sending, false);
});

test("reset during a reply invalidates delayed chunks and persisted history", async () => {
  let release: () => void = () => undefined;
  const saved = storage();
  const chat = createDemoChat(saved, () => new Promise<void>((resolve) => { release = resolve; }));
  const pending = chat.send({ content: "旧的消息", attachments: [], replyTarget: null });
  chat.reset();
  release();
  await pending;
  assert.equal(chat.getSnapshot().messages.length, 1);
  assert.equal(createDemoChat(saved).getSnapshot().messages.length, 1);
});

test("a storage write failure reports the problem once without rejecting the send callback", async () => {
  let writes = 0;
  const chat = createDemoChat({ getItem: () => null, setItem: () => { writes += 1; throw new Error("Storage full"); }, removeItem: () => undefined }, async () => undefined);
  assert.equal(await chat.send({ content: "你好", attachments: [], replyTarget: null }), true);
  assert.equal(writes, 1);
  assert.match(chat.getSnapshot().error, /无法保存演示记录/);
  assert.equal(chat.getSnapshot().sending, false);
});

test("blocked storage reads propagate to the page error boundary", () => {
  assert.throws(() => createDemoChat({ getItem: () => { throw new Error("Storage blocked"); }, setItem: () => undefined, removeItem: () => undefined }), /Storage blocked/);
});

test("invalid sample indices reset and forged message capabilities are discarded on reload", () => {
  const base = { sampleIndex: -1, messages: [{ role: "assistant", content: "文字", media: ["private.png"], tool_chain: [null], metadata: { reply_to_content: {}, reply_to_sender: "栞" } }], mood: "平静", thought: "样例" };
  const invalid = createDemoChat({ getItem: () => JSON.stringify(base), setItem: () => undefined, removeItem: () => undefined });
  assert.equal(invalid.getSnapshot().sampleIndex, 0);
  const restored = createDemoChat({ getItem: () => JSON.stringify({ ...base, sampleIndex: 1 }), setItem: () => undefined, removeItem: () => undefined });
  const message = restored.getSnapshot().messages[0];
  assert.equal(message.media, undefined);
  assert.equal(message.tool_chain, undefined);
  assert.deepEqual(message.metadata, { reply_to_sender: "栞" });
});
