import assert from "node:assert/strict";
import { before, test } from "node:test";
import { act } from "react";
import { changeInputValue, mountTestComponent } from "@shiori/plugin-sdk/testing";
import type { PhoneConversation } from "./phoneClient";
import type { PhoneApp } from "./phonePresentation";

// Base UI's dialog reads browser globals when it loads: import after a window exists.
let PhoneConversationScreens: typeof import("./PhoneConversationScreens").PhoneConversationScreens;
before(async () => {
  const view = await mountTestComponent(null);
  ({ PhoneConversationScreens } = await import("./PhoneConversationScreens"));
  await view.cleanup();
});

const role = { id: "mira", name: "Mira", avatar_abs: "" };
const app: PhoneApp = { accountId: "qq:1", label: "QQ", accountName: "小栞", offline: false };
const conversation: PhoneConversation = {
  threadId: "thread:mira:qq:gqq:5", accountId: "qq:1", channel: "qq", chatType: "group", displayName: "摸鱼群",
  isUserChat: false,
  lastMessage: { role: "assistant", content: "我来", timestamp: "2026-09-29T10:02:00+08:00", hasMedia: false, senderName: null },
};

const message = (id: string, patch: Record<string, unknown>) => ({
  id, seq: null, sender: "other", sender_id: "42", sender_name: "阿花", sender_is_user: false,
  content: id, media: [], timestamp: "2026-09-29T10:00:00+08:00", ...patch,
});

const member = { channel: "qq", sender_id: "42", call_name: "阿花", nicknames: ["花花", "阿花"], brief: "爱开黑", profile: "## 印象" };

test("group chat info: blocks, note saved and its draft kept, recent activity read-only; a profile opens from the list and is deleted", async () => {
  const calls: Array<{ method: string; payload: Record<string, unknown> }> = [];
  const replies: Record<string, unknown> = {
    "phone.conversation.messages": { has_more: false, next_before_seq: null, messages: [
      message("谁来开黑", {}),
      message("我也来", { sender_id: "100", sender_name: "主人", sender_is_user: true }),
      message("我来", { sender: "role", sender_id: null, sender_name: null }),
    ] },
    "phone.conversation.note": { note: "旧笔记" },
    "phone.conversation.note.save": { note: "新笔记" },
    "phone.conversation.activity": { recent_activity: "在聊开黑" },
    "phone.conversation.members": { members: [member] },
    "phone.member.profile": { member },
    "phone.member.profile.delete": { channel: "qq", sender_id: "42" },
  };
  const view = await mountTestComponent(
    <PhoneConversationScreens role={role} app={app} conversation={conversation} now={new Date("2026-09-29T12:00:00+08:00")} onBack={() => {}} />,
    { windowGlobals: { miraDesktop: {
      localAssetUrl: (path: string) => path,
      onEvent: () => () => {},
      invoke: async ({ method, payload }: { method: string; payload: Record<string, unknown> }) => {
        calls.push({ method, payload });
        // Once deleted, the member is gone from the list.
        if (method === "phone.member.profile.delete") replies["phone.conversation.members"] = { members: [] };
        return { id: "response", type: "response", method, error: null, payload: replies[method] };
      },
    } } },
  );
  const find = <T extends Element = HTMLElement>(testId: string) => view.container.querySelector<T & HTMLElement>(`[data-testid="${testId}"]`);
  const click = (element: HTMLElement | null | undefined) => act(async () => element?.click());
  try {
    // Only the other, identified sender's avatar opens a profile; the user's does not.
    assert.equal(view.container.querySelectorAll('[data-testid="phone-member-avatar"]').length, 1);

    await click(find("phone-chat-info"));
    assert.deepEqual(
      Array.from(find("phone-chat-info-page")?.querySelectorAll("section") ?? [], (section) => section.getAttribute("aria-label")),
      ["群信息", "群成员", "群笔记", "最近动态"],
    );
    assert.match(find("phone-info-summary")?.textContent ?? "", /摸鱼群.*QQ.*小栞/);
    assert.equal(find("phone-info-activity-text")?.textContent, "在聊开黑");
    assert.equal(find("phone-info-activity")?.querySelector("textarea, input"), null);

    const note = find<HTMLTextAreaElement>("phone-info-note-input");
    assert.equal(note?.value, "旧笔记");
    assert.equal(find("phone-info-note-save"), null);
    await changeInputValue(note!, "新笔记");
    await click(find("phone-info-note-save"));
    const saved = calls.find((call) => call.method === "phone.conversation.note.save");
    assert.deepEqual(saved?.payload, { role_id: "mira", thread_id: conversation.threadId, note: "新笔记" });

    // An unsaved note survives a visit to a member's profile.
    await changeInputValue(find<HTMLTextAreaElement>("phone-info-note-input")!, "草稿");
    await click(find("phone-info-member-42"));
    assert.equal(find<HTMLInputElement>("phone-member-brief")?.value, "爱开黑");
    assert.equal(find("phone-member-nicknames")?.textContent, "花花阿花");
    const backs = () => Array.from(view.container.querySelectorAll<HTMLButtonElement>('[data-testid="phone-back"]'));
    await click(backs().at(-1));
    assert.equal(find("phone-member-profile"), null);
    assert.equal(find<HTMLTextAreaElement>("phone-info-note-input")?.value, "草稿");

    await click(find("phone-info-member-42"));
    await click(find("phone-member-delete"));
    assert.match(document.querySelector('[role="dialog"]')?.textContent ?? "", /同一渠道的所有群共用/);
    const confirm = Array.from(document.querySelectorAll<HTMLButtonElement>('[role="dialog"] button'))
      .find((button) => button.textContent === "确认删除");
    await click(confirm);
    assert.ok(calls.some((call) => call.method === "phone.member.profile.delete" && call.payload.sender_id === "42"));
    // Back where the profile was opened from.
    assert.equal(find("phone-member-profile"), null);
    assert.equal(find<HTMLTextAreaElement>("phone-info-note-input")?.value, "草稿");
    // The kept-mounted info page reread its member list.
    assert.equal(find("phone-info-member-42"), null);
  } finally { await view.cleanup(); }
});
