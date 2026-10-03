import assert from "node:assert/strict";
import { test } from "node:test";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import type { PhoneConversation } from "./phoneClient";
import { PhoneConversationList } from "./PhoneConversationList";

const conversation = (threadId: string, avatarPath: string | null): PhoneConversation => ({
  threadId, accountId: "qq:1", channel: "qq", chatType: "group", displayName: threadId, avatarPath, isUserChat: false,
  listeningSupported: false,
  lastMessage: { role: "user", content: "在吗", timestamp: "2026-09-29T10:00:00+08:00", hasMedia: false, senderName: null },
});

test("a row shows the cached chat avatar, or its chat type mark without one", async () => {
  const view = await mountTestComponent(
    <PhoneConversationList
      app={{ accountId: "qq:1", label: "QQ", accountName: "小栞", offline: false }}
      conversations={[conversation("with", "D:/avatars/chat/group.png"), conversation("without", null)]}
      error="" now={new Date("2026-09-29T12:00:00+08:00")} onRetry={() => {}} onBack={() => {}} onOpen={() => {}}
    />,
    { windowGlobals: { miraDesktop: { localAssetUrl: (path: string) => `asset:${path}` } } },
  );
  const avatar = (threadId: string) => view.container.querySelector(`[data-testid="phone-conversation-${threadId}"]`)?.firstElementChild;
  try {
    assert.equal(avatar("with")?.querySelector("img")?.getAttribute("src"), "asset:D:/avatars/chat/group.png");
    assert.equal(avatar("without")?.querySelector("img"), null);
    assert.ok(avatar("without")?.querySelector("svg"));
  } finally {
    await view.cleanup();
  }
});
