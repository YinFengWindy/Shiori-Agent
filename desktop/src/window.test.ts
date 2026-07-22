import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import type { BrowserWindow } from "electron";
import { attachDesktopWindowLifecycle, shouldHideDesktopWindowOnClose } from "./windowLifecycle.js";

class FakeWindow extends EventEmitter {
  hidden = false;

  hide(): void {
    this.hidden = true;
  }
}

test("main window close is hidden while the desktop pet is running", () => {
  assert.equal(shouldHideDesktopWindowOnClose({
    isQuitting: false,
    trayLifecycleEnabled: false,
    desktopPetRunning: true,
  }), true);
});

test("explicit app quit still allows the main window to close", () => {
  assert.equal(shouldHideDesktopWindowOnClose({
    isQuitting: true,
    trayLifecycleEnabled: true,
    desktopPetRunning: true,
  }), false);
});

test("closing the main window hides the shell instead of allowing a native close", () => {
  const window = new FakeWindow();
  let prevented = false;
  attachDesktopWindowLifecycle(window as unknown as BrowserWindow, {
    shouldHideOnClose: () => true,
  });

  window.emit("close", {
    preventDefault: () => {
      prevented = true;
    },
  });

  assert.equal(prevented, true);
  assert.equal(window.hidden, true);
});
