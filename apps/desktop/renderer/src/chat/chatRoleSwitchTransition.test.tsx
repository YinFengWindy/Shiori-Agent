/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { openChatRole } from "./chatRoleSwitchTransition";

/** The chat surface's marked parts, as ChatSurface / ChatHeader / RoleSidebar render them. */
function ChatStage() {
  return (
    <div>
      <button type="button" data-chat-role-row="rin"><img data-vt-part="avatar" alt="" /><span data-vt-part="name">雨宫凛</span></button>
      <button type="button" data-chat-role-row="natsu"><img data-vt-part="avatar" alt="" /><span data-vt-part="name">千夏</span></button>
      <div data-chat-backdrop="" />
      <header data-chat-header=""><img data-vt-part="avatar" alt="" /><span data-vt-part="name">雨宫凛</span></header>
      <section data-chat-conversation="" />
    </div>
  );
}

/** Installs a fake `document.startViewTransition` recording the names present before and after the update. */
function recordTransition() {
  const names = { before: [] as string[], after: [] as string[] };
  const read = () => Array.from(document.querySelectorAll<HTMLElement>("[data-view-transition-named]"))
    .map((element) => `${element.closest("[data-chat-role-row]")?.getAttribute("data-chat-role-row") ?? element.tagName.toLowerCase()}:${element.style.viewTransitionName}`)
    .sort();
  Object.defineProperty(document, "startViewTransition", {
    configurable: true,
    value(update: () => void) {
      names.before = read();
      const updateCallbackDone = Promise.resolve().then(() => {
        update();
        names.after = read();
      });
      return { updateCallbackDone, finished: updateCallbackDone, skipTransition: () => undefined };
    },
  });
  return names;
}

describe("openChatRole", () => {
  it("morphs the picked row's avatar and name into the header and names every chat layer", async () => {
    const view = await mountTestComponent(<ChatStage />);
    try {
      const names = recordTransition();
      let opened = 0;
      await openChatRole({ roleId: "natsu", activeRoleId: "rin", chatShown: true, open: () => { opened += 1; } });
      assert.equal(opened, 1);
      assert.deepEqual(names.before, [
        "div:chat-backdrop",
        "header:chat-header",
        "img:chat-role-avatar-old",
        "natsu:chat-role-avatar",
        "natsu:chat-role-name",
        "section:chat-conversation",
        "span:chat-role-name-old",
      ]);
      assert.deepEqual(names.after, [
        "div:chat-backdrop",
        "header:chat-header",
        "img:chat-role-avatar",
        "section:chat-conversation",
        "span:chat-role-name",
      ]);
      assert.equal(document.querySelectorAll("[data-view-transition-named]").length, 0, "names are cleared afterwards");
    } finally {
      await view.cleanup();
    }
  });

  it("opens directly when re-picking the open role or when the chat is not on screen", async () => {
    const view = await mountTestComponent(<ChatStage />);
    try {
      let started = 0;
      Object.defineProperty(document, "startViewTransition", { configurable: true, value: () => { started += 1; } });
      let opened = 0;
      await openChatRole({ roleId: "rin", activeRoleId: "rin", chatShown: true, open: () => { opened += 1; } });
      await openChatRole({ roleId: "natsu", activeRoleId: "rin", chatShown: false, open: () => { opened += 1; } });
      assert.equal(opened, 2);
      assert.equal(started, 0);
    } finally {
      await view.cleanup();
    }
  });
});
