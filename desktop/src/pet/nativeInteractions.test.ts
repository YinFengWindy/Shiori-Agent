import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import type { BrowserWindow } from "electron";
import {
  attachDesktopPetNativeInteractions,
  windowsNonClientLeftButtonDoubleClick,
} from "./nativeInteractions.js";

class FakeNativePetWindow extends EventEmitter {
  private readonly windowMessageHandlers = new Map<number, () => void>();
  readonly webContents = new EventEmitter();

  hookWindowMessage(message: number, callback: () => void): void {
    this.windowMessageHandlers.set(message, callback);
  }

  emitWindowMessage(message: number): void {
    this.windowMessageHandlers.get(message)?.();
  }
}

test("native desktop pet interactions preserve double click and context menu commands", () => {
  const window = new FakeNativePetWindow();
  let openCount = 0;
  let contextMenuCount = 0;
  let prevented = false;

  attachDesktopPetNativeInteractions({
    window: window as unknown as BrowserWindow,
    platform: "win32",
    onOpenPetRole: () => {
      openCount += 1;
    },
    onShowContextMenu: () => {
      contextMenuCount += 1;
    },
  });

  window.emitWindowMessage(windowsNonClientLeftButtonDoubleClick);
  window.emit("system-context-menu", { preventDefault: () => { prevented = true; } });

  assert.equal(openCount, 1);
  assert.equal(contextMenuCount, 1);
  assert.equal(prevented, true);
});

test("native mouse double click restores the desktop window when the drag region omits a double-click message", () => {
  const window = new FakeNativePetWindow();
  let openCount = 0;

  attachDesktopPetNativeInteractions({
    window: window as unknown as BrowserWindow,
    platform: "win32",
    onOpenPetRole: () => {
      openCount += 1;
    },
    onShowContextMenu: () => undefined,
  });

  window.webContents.emit("before-mouse-event", {}, { type: "mouseDown", button: "left", clickCount: 2 });

  assert.equal(openCount, 1);
});
