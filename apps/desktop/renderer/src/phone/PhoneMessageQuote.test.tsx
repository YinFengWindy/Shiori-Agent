import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import { PhoneMessageQuote } from "./PhoneMessageQuote";

test("a long quote starts clamped and expands on click; its pictures open enlarged", async () => {
  const content = "这是一段很长的被引用原文，".repeat(5);
  const opened: string[] = [];
  const view = await mountTestComponent(
    <PhoneMessageQuote quote={{ label: "7", content, media: ["D:/media/quoted.png"], collapsible: true }}
      onOpenImage={(path) => opened.push(path)} />,
    { windowGlobals: { miraDesktop: { localAssetUrl: (path: string) => path } } },
  );
  try {
    const toggle = view.container.querySelector<HTMLButtonElement>("button[aria-expanded]");
    // The quoted text itself names the toggle.
    assert.equal(toggle?.textContent, content);
    assert.equal(toggle?.hasAttribute("aria-label"), false);
    assert.equal(toggle?.getAttribute("aria-expanded"), "false");
    await act(async () => toggle?.click());
    assert.equal(toggle?.getAttribute("aria-expanded"), "true");
    await act(async () => view.container.querySelector<HTMLButtonElement>('button[aria-label="查看大图"]')?.click());
    assert.deepEqual(opened, ["D:/media/quoted.png"]);
  } finally {
    await view.cleanup();
  }
});
