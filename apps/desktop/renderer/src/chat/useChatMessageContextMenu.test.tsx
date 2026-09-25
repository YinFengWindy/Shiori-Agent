/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React, { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { SessionMessage } from "../shared/types";
import { getChatMessageActionAvailability } from "./chatMessageActions";
import { ChatMessageContextMenu } from "./ChatMessageContextMenu";
import { ChatMessageRow } from "./ChatMessageRow";
import { useChatMessageContextMenu } from "./useChatMessageContextMenu";

const message: SessionMessage = { id: "m1", seq: 1, role: "assistant", content: "早上好", timestamp: "" };

/** One real message row wired to the hook and the menu, the way ChatSurface does it. */
function Harness({ log }: { log: string[] }) {
  const contextMenu = useChatMessageContextMenu();
  const menu = contextMenu.menu;
  return (
    <>
      <ChatMessageRow
        activeRole={null}
        index={0}
        renderKey="m1"
        isHighlighted={false}
        message={message}
        animateEnter={false}
        sending={false}
        retryable={false}
        channelCatalog={null}
        onBeginAttachmentDrag={() => undefined}
        onJumpToMessage={() => undefined}
        onOpenContextMenu={contextMenu.open}
        onOpenImagePreview={() => undefined}
        onRetryMessage={() => undefined}
      />
      <button type="button">elsewhere</button>
      {menu ? (
        <ChatMessageContextMenu
          menu={menu}
          menuRef={contextMenu.menuRef}
          availability={getChatMessageActionAvailability(menu.message, { sending: false, retryable: false })}
          onCopy={() => { log.push("copy"); contextMenu.close(); }}
          onQuote={() => { log.push("quote"); contextMenu.close(); }}
          onRetry={() => { log.push("retry"); contextMenu.close(); }}
          onClose={contextMenu.close}
        />
      ) : null}
    </>
  );
}

function article(): HTMLElement {
  const element = document.querySelector<HTMLElement>('[data-message-key]');
  assert.ok(element);
  return element;
}

function menu(): HTMLElement | null {
  return document.querySelector<HTMLElement>('[data-testid="message-context-menu"]');
}

async function keyDown(key: string, init: KeyboardEventInit = {}) {
  await act(async () => {
    (document.activeElement ?? document.body).dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init }));
  });
}

describe("useChatMessageContextMenu", () => {
  it("makes messages focusable and opens the menu from Shift+F10 with focus on its first action", async () => {
    const view = await mountTestComponent(<Harness log={[]} />);
    try {
      assert.equal(article().tabIndex, 0);
      assert.equal(article().getAttribute("aria-keyshortcuts"), "Shift+F10 ContextMenu");
      await act(async () => { article().focus(); });
      await keyDown("F10", { shiftKey: true });
      assert.ok(menu());
      assert.equal(document.activeElement?.getAttribute("data-testid"), "message-context-menu-copy");
    } finally { await view.cleanup(); }
  });

  it("opens from the menu key and walks the actions with the arrow keys", async () => {
    const log: string[] = [];
    const view = await mountTestComponent(<Harness log={log} />);
    try {
      await act(async () => { article().focus(); });
      await keyDown("ContextMenu");
      await keyDown("ArrowDown");
      assert.equal(document.activeElement?.getAttribute("data-testid"), "message-context-menu-quote");
      await keyDown("ArrowDown");
      assert.equal(document.activeElement?.getAttribute("data-testid"), "message-context-menu-copy");
      await act(async () => { (document.activeElement as HTMLButtonElement).click(); });
      assert.deepEqual(log, ["copy"]);
      assert.equal(menu(), null);
      assert.equal(document.activeElement, article(), "choosing an action hands focus back to the message");
    } finally { await view.cleanup(); }
  });

  it("treats the browser's keyboard-synthesized contextmenu (button -1) like the key itself", async () => {
    const view = await mountTestComponent(<Harness log={[]} />);
    try {
      await act(async () => { article().focus(); });
      await act(async () => { article().dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, button: -1 })); });
      assert.equal(document.activeElement?.getAttribute("data-testid"), "message-context-menu-copy");
    } finally { await view.cleanup(); }
  });

  it("returns focus to the message on Escape and on Tab", async () => {
    const view = await mountTestComponent(<Harness log={[]} />);
    try {
      await act(async () => { article().focus(); });
      await keyDown("F10", { shiftKey: true });
      await keyDown("Escape");
      assert.equal(menu(), null);
      assert.equal(document.activeElement, article());

      await keyDown("F10", { shiftKey: true });
      await keyDown("Tab");
      assert.equal(menu(), null);
      assert.equal(document.activeElement, article());
    } finally { await view.cleanup(); }
  });

  it("opens a right-click menu at the pointer without moving focus, and dismisses it on an outside pointer-down", async () => {
    const view = await mountTestComponent(<Harness log={[]} />);
    try {
      const elsewhere = Array.from(document.querySelectorAll("button")).find((button) => button.textContent === "elsewhere");
      await act(async () => { elsewhere?.focus(); });
      await act(async () => { article().dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, cancelable: true, button: 2, clientX: 200, clientY: 150 })); });
      assert.equal(menu()?.style.left, "200px");
      assert.equal(menu()?.style.top, "150px");
      assert.equal(document.activeElement, elsewhere);
      await act(async () => { document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true })); });
      assert.equal(menu(), null);
      assert.equal(document.activeElement, elsewhere);
    } finally { await view.cleanup(); }
  });

  it("ignores other keys on a focused message", async () => {
    const view = await mountTestComponent(<Harness log={[]} />);
    try {
      await act(async () => { article().focus(); });
      await keyDown("F10");
      await keyDown("Enter", { shiftKey: true });
      assert.equal(menu(), null);
    } finally { await view.cleanup(); }
  });
});
