import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  clampChatMessageContextMenuPoint,
  getKeyboardChatMessageContextMenuPoint,
  isChatMessageContextMenuKey,
} from "./chatMessageContextMenuPlacement";

const viewport = { width: 1280, height: 800 };

describe("chatMessageContextMenuPlacement", () => {
  it("recognizes the menu key and Shift+F10, nothing else", () => {
    assert.equal(isChatMessageContextMenuKey({ key: "ContextMenu", shiftKey: false }), true);
    assert.equal(isChatMessageContextMenuKey({ key: "F10", shiftKey: true }), true);
    assert.equal(isChatMessageContextMenuKey({ key: "F10", shiftKey: false }), false);
    assert.equal(isChatMessageContextMenuKey({ key: "Enter", shiftKey: true }), false);
  });

  it("opens a pointer menu at the pointer, pulled back in near the right and bottom edges", () => {
    assert.deepEqual(clampChatMessageContextMenuPoint({ x: 400, y: 300 }, viewport), { x: 400, y: 300 });
    assert.deepEqual(clampChatMessageContextMenuPoint({ x: 1270, y: 790 }, viewport), { x: 1132, y: 680 });
  });

  it("opens a keyboard menu just under the start of the bubble", () => {
    assert.deepEqual(getKeyboardChatMessageContextMenuPoint({ left: 420, bottom: 360 }, viewport), { x: 420, y: 364 });
  });

  it("keeps a keyboard menu on screen when the bubble runs past the viewport", () => {
    assert.equal(getKeyboardChatMessageContextMenuPoint({ left: 420, bottom: 1500 }, viewport).y, 680);
    assert.equal(getKeyboardChatMessageContextMenuPoint({ left: 420, bottom: -40 }, viewport).y, 12);
  });
});
