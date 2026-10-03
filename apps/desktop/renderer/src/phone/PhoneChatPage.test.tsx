import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import type { BridgeEvent } from "@yinfengwindy/shiori-sdk";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { PhoneConversation } from "./phoneClient";

// Base UI's dialog reads browser globals when it loads: import after a window exists.
let PhoneChatPage: typeof import("./PhoneChatPage").PhoneChatPage;
before(async () => {
  const view = await mountTestComponent(null);
  ({ PhoneChatPage } = await import("./PhoneChatPage"));
  await view.cleanup();
});

const role = { id: "mira", name: "Mira", avatar_abs: "" };

const conversation: PhoneConversation = {
  threadId: "thread:mira:qq:gqq:5", accountId: "qq:1", channel: "qq", chatType: "group", displayName: "摸鱼群",
  avatarPath: null, isUserChat: false, listeningSupported: true,
  lastMessage: { role: "assistant", content: "我来", timestamp: "2026-09-29T10:02:00+08:00", hasMedia: false, senderName: null },
};

const row = (id: string, patch: Record<string, unknown> = {}) => ({
  id, seq: null, sender: "other", sender_id: "42", sender_name: "阿花", sender_is_user: false, sender_avatar_abs: null,
  mentions: [], quote: null, content: id, media: [], timestamp: "2026-09-29T10:00:00+08:00", listened: false, ...patch,
});

const liveEvent = (threadId: string, messages: ReturnType<typeof row>[]): BridgeEvent => ({
  id: "phone", type: "event", method: "phone.conversation.updated",
  payload: {
    role_id: "mira", thread_id: threadId, messages,
    conversation: {
      thread_id: threadId, account_id: "qq:1", channel: "qq", chat_type: "group", display_name: "摸鱼群",
      avatar_abs: null, is_user_chat: false, listening_supported: true,
      last_message: { role: "user", content: "", timestamp: "", has_media: false, sender_name: null },
    },
  },
});

test("the chat page shows the conversation from the role's side and takes its new messages live, once", async () => {
  const listeners = new Set<(event: BridgeEvent) => void>();
  const emit = (event: BridgeEvent) => listeners.forEach((listener) => listener(event));
  let unsubscribed = false;
  const view = await mountTestComponent(
    <PhoneChatPage role={role} conversation={conversation} now={new Date("2026-09-29T12:00:00+08:00")} onBack={() => {}} />,
    { windowGlobals: { miraDesktop: {
      localAssetUrl: (path: string) => path,
      onEvent: (listener: (event: BridgeEvent) => void) => {
        listeners.add(listener);
        return () => { listeners.delete(listener); unsubscribed = !listeners.size; };
      },
      invoke: async ({ method }: { method: string }) => ({
        id: "response", type: "response", method, error: null,
        payload: method === "phone.listening.messages" ? { has_more: false, next_before_seq: null, messages: [] } : {
          thread_id: conversation.threadId, has_more: false, next_before_seq: 1, messages: [
          row("谁来开黑", { seq: 1, sender_avatar_abs: "D:/avatars/sender/42.png" }),
          row("我也来", { seq: 2, sender_id: "100", sender_name: "主人", sender_is_user: true, media: ["D:/media/cat.png"] }),
          row("我来", { seq: 3, sender: "role", sender_id: null, sender_name: null }),
        ] },
      }),
    } } },
  );
  const messages = () => Array.from(view.container.querySelectorAll("[data-side]"), (item) => (
    `${item.getAttribute("data-side")}:${item.querySelector("p")?.textContent}`
  ));
  try {
    assert.deepEqual(messages(), ["left:谁来开黑", "left:我也来", "right:我来"]);
    // A cached sender avatar shows beside the message; without one the placeholder stays.
    const leftAvatars = Array.from(view.container.querySelectorAll('[data-side="left"]'), (item) => item.firstElementChild);
    assert.deepEqual(
      leftAvatars.map((avatar) => avatar?.querySelector("img")?.getAttribute("src") ?? avatar?.querySelector("svg")?.tagName),
      ["D:/avatars/sender/42.png", "svg"],
    );
    const marked = view.container.querySelector('[data-testid="phone-message-me"]')?.closest("[data-side]");
    assert.equal(marked?.querySelector("p")?.textContent, "我也来");
    assert.match(marked?.textContent ?? "", /主人/);
    // Its picture opens enlarged.
    await act(async () => marked?.querySelector<HTMLButtonElement>('button[aria-label="查看大图"]')?.click());
    assert.equal(document.querySelector('[role="dialog"] img')?.getAttribute("src"), "D:/media/cat.png");

    await act(async () => emit(liveEvent(conversation.threadId, [row("我来"), row("新消息")])));
    await act(async () => emit(liveEvent("thread:mira:qq:gqq:6", [row("别的群")])));
    // A record the group's listening just stored joins too, marked as heard.
    await act(async () => emit({ id: "phone", type: "event", method: "phone.listening.heard", payload: {
      role_id: "mira", thread_id: conversation.threadId, message: row("听到的", { id: "listen:1", listened: true }),
    } }));
    assert.deepEqual(messages(), ["left:谁来开黑", "left:我也来", "right:我来", "left:新消息", "left:听到的"]);
    assert.ok(view.container.querySelector('[data-testid="phone-message-listen:1"]')?.hasAttribute("data-listened"));
  } finally { await view.cleanup(); }
  assert.equal(unsubscribed, true);
});
