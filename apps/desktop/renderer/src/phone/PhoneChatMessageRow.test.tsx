import assert from "node:assert/strict";
import { test } from "node:test";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import { PhoneChatMessageRow } from "./PhoneChatMessageRow";

test("a quote sits above the bubble, the message's own picture outside it", async () => {
  const view = await mountTestComponent(
    <ul>
      <PhoneChatMessageRow role={{ name: "Mira", avatar_abs: "" }} onOpenImage={() => {}} item={{
        kind: "message", key: "m", side: "left", senderLabel: "阿花", isUser: false, mentionLabels: [],
        quote: { label: "7", content: "看", media: ["D:/media/quoted.png"], collapsible: false },
        message: {
          id: "m", seq: 1, sender: "other", senderId: "42", senderName: "阿花", senderIsUser: false, senderAvatarPath: null,
          mentions: [], quote: null, content: "看这个", media: ["D:/media/own.png"], timestamp: "", listened: false,
        },
      }} />
    </ul>,
    { windowGlobals: { miraDesktop: { localAssetUrl: (path: string) => path } } },
  );
  try {
    const quote = view.container.querySelector('[data-testid="phone-message-quote"]');
    const bubble = view.container.querySelector("p");
    assert.ok(quote && bubble && quote.compareDocumentPosition(bubble) & Node.DOCUMENT_POSITION_FOLLOWING);
    const pictures = Array.from(view.container.querySelectorAll('button[aria-label="查看大图"]'));
    assert.deepEqual(pictures.map((button) => quote.contains(button)), [true, false]);
  } finally {
    await view.cleanup();
  }
});
