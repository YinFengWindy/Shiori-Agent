import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import type { BridgeEvent } from "../../../src/bridge/shared";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { PhoneConversation } from "./phoneClient";
import { PhoneChatPage } from "./PhoneChatPage";

const role = { id: "mira", name: "Mira", avatar_abs: "" };

const conversation: PhoneConversation = {
  threadId: "thread:mira:qq:gqq:5", accountId: "qq:1", channel: "qq", chatType: "group", displayName: "摸鱼群",
  isUserChat: false,
  lastMessage: { role: "assistant", content: "我来", timestamp: "2026-09-29T10:02:00+08:00", hasMedia: false, senderName: null },
};

const row = (id: string, patch: Record<string, unknown> = {}) => ({
  id, seq: null, sender: "other", sender_id: "42", sender_name: "阿花", sender_is_user: false,
  content: id, media: [], timestamp: "2026-09-29T10:00:00+08:00", ...patch,
});

const liveEvent = (threadId: string, messages: ReturnType<typeof row>[]): BridgeEvent => ({
  id: "phone", type: "event", method: "phone.conversation.updated",
  payload: {
    role_id: "mira", thread_id: threadId, messages,
    conversation: {
      thread_id: threadId, account_id: "qq:1", channel: "qq", chat_type: "group", display_name: "摸鱼群",
      is_user_chat: false, last_message: { role: "user", content: "", timestamp: "", has_media: false, sender_name: null },
    },
  },
});

test("the chat page shows the conversation from the role's side and takes its new messages live, once", async () => {
  let emit: ((event: BridgeEvent) => void) | undefined;
  let unsubscribed = false;
  const view = await mountTestComponent(
    <PhoneChatPage role={role} conversation={conversation} now={new Date("2026-09-29T12:00:00+08:00")} onBack={() => {}} />,
    { windowGlobals: { miraDesktop: {
      onEvent: (listener: (event: BridgeEvent) => void) => {
        emit = listener;
        return () => { unsubscribed = true; };
      },
      invoke: async ({ method }: { method: string }) => ({
        id: "response", type: "response", method, error: null,
        payload: { thread_id: conversation.threadId, has_more: false, next_before_seq: 1, messages: [
          row("谁来开黑", { seq: 1 }),
          row("我也来", { seq: 2, sender_id: "100", sender_name: "主人", sender_is_user: true }),
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
    const marked = view.container.querySelector('[data-testid="phone-message-me"]')?.closest("[data-side]");
    assert.equal(marked?.querySelector("p")?.textContent, "我也来");
    assert.match(marked?.textContent ?? "", /主人/);

    await act(async () => emit?.(liveEvent(conversation.threadId, [row("我来"), row("新消息")])));
    await act(async () => emit?.(liveEvent("thread:mira:qq:gqq:6", [row("别的群")])));
    assert.deepEqual(messages(), ["left:谁来开黑", "left:我也来", "right:我来", "left:新消息"]);
  } finally { await view.cleanup(); }
  assert.equal(unsubscribed, true);
});
