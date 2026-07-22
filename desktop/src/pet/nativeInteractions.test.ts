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
