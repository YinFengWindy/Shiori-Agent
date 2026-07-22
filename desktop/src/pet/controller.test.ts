import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import type { BrowserWindow } from "electron";
import { DesktopPetController } from "./controller.js";
import type { DesktopPetSettings } from "./types.js";

class FakePetWebContents {
  send(): void {}
}

class FakePetWindow extends EventEmitter {
  private position: [number, number] = [0, 0];
  readonly webContents = new FakePetWebContents();

  isDestroyed(): boolean {
    return false;
  }

  showInactive(): void {}

  setPosition(x: number, y: number): void {
    this.position = [x, y];
    queueMicrotask(() => this.emit("moved"));
  }

  getPosition(): [number, number] {
    return this.position;
  }

  getBounds() {
    return { x: this.position[0], y: this.position[1], width: 192, height: 208 };
  }

  destroy(): void {
    this.emit("closed");
  }
}

test("desktop pet moves immediately from a renderer drag command and persists the position", async () => {
  let settings: DesktopPetSettings = { visible: false, roleId: null, packageId: null, positions: {} };
  let saveCount = 0;
  const window = new FakePetWindow();
  const controller = new DesktopPetController({
    getSettings: () => settings,
    saveSettings: async (nextSettings) => {
      saveCount += 1;
      settings = nextSettings;
    },
    resolveBinding: async () => ({
      roleId: "role-1",
      package: { id: "pet-1", displayName: "Pet", spritesheetUrl: "mira-asset://pet" },
    }),
    createWindow: () => window as unknown as BrowserWindow,
    displayForWindow: () => ({ id: "display-1", workArea: { x: 0, y: 0, width: 1920, height: 1080 } }),
    openLocalAttachment: () => undefined,
  });

  await controller.show();
  await new Promise((resolve) => setImmediate(resolve));
  saveCount = 0;
  controller.moveTo(460, 460);
  assert.deepEqual(window.getPosition(), [460, 460]);
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(saveCount, 1);
  assert.deepEqual(settings.positions["role-1:display-1"], { x: 460, y: 460 });
});
