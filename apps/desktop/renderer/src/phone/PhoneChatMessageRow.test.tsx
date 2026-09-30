import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import { PhoneChatMessageRow } from "./PhoneChatMessageRow";
import { phoneChatItems } from "./phoneChatPresentation";
import type { PhoneMessage } from "./phoneClient";

const message: PhoneMessage = {
  id: "m", seq: 1, sender: "other", senderId: "42", senderName: "阿花", senderIsUser: false, senderAvatarPath: null,
  mentions: [],
  quote: { senderId: "7", name: null, content: "这是一段很长的被引用原文，".repeat(5), media: ["D:/media/quoted.png"] },
  content: "看这个", media: ["D:/media/own.png"], timestamp: "2026-09-29T10:00:00+08:00", listened: false,
};

test("a quoted message sits above the bubble, its pictures apart from the message's own, long text expandable", async () => {
  const [item] = phoneChatItems([message], new Date("2026-09-29T12:00:00+08:00")).filter((line) => line.kind === "message");
  assert.ok(item?.kind === "message");
  const opened: string[] = [];
  const view = await mountTestComponent(
    <ul><PhoneChatMessageRow item={item} role={{ name: "Mira", avatar_abs: "" }} onOpenImage={(path) => opened.push(path)} /></ul>,
    { windowGlobals: { miraDesktop: { localAssetUrl: (path: string) => path } } },
  );
  try {
    const quote = view.container.querySelector('[data-testid="phone-message-quote"]');
    // No name known: the quoted sender's ID stands in.
    assert.match(quote?.textContent ?? "", /^7这是一段很长的被引用原文/);
    const toggle = quote?.querySelector<HTMLButtonElement>("button[aria-expanded]");
    assert.equal(toggle?.getAttribute("aria-expanded"), "false");
    await act(async () => toggle?.click());
    assert.equal(toggle?.getAttribute("aria-expanded"), "true");
    await act(async () => quote?.querySelector<HTMLButtonElement>('button[aria-label="查看大图"]')?.click());
    assert.deepEqual(opened, ["D:/media/quoted.png"]);
    // The message's own picture stays outside the quote block.
    const pictures = Array.from(view.container.querySelectorAll('button[aria-label="查看大图"]'));
    assert.equal(pictures.filter((button) => !quote?.contains(button)).length, 1);
  } finally {
    await view.cleanup();
  }
});
