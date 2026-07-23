import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import test from "node:test";
import type { BrowserWindow } from "electron";
import { DesktopPetController } from "./controller.js";
import type { DesktopPetSettings } from "./types.js";

class FakePetWebContents extends EventEmitter {
  readonly states: string[] = [];
  readonly messages: Array<{ channel: string; payload: unknown }> = [];

  send(channel: string, payload: { state?: string }): void {
    this.messages.push({ channel, payload });
    if (payload.state) this.states.push(payload.state);
  }
}

class FakePetWindow extends EventEmitter {
  private position: [number, number] = [0, 0];
  readonly webContents = new FakePetWebContents();
  showCount = 0;
  readonly boundsWrites: Array<{ x: number; y: number; width: number; height: number }> = [];

  isDestroyed(): boolean {
    return false;
  }

  showInactive(): void {
    this.showCount += 1;
  }

  hookWindowMessage(): void {}

  setPosition(x: number, y: number): void {
    this.position = [x, y];
    queueMicrotask(() => {
      this.emit("move");
      this.emit("moved");
    });
  }

  setBounds(bounds: { x: number; y: number; width: number; height: number }): void {
    this.boundsWrites.push(bounds);
    this.setPosition(bounds.x, bounds.y);
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

test("desktop pet persists only the final system-cursor position after a drag", async () => {
  let settings: DesktopPetSettings = { visible: false, roleId: null, packageId: null, positions: {} };
  let saveCount = 0;
  let cursor = { x: 532, y: 564 };
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
    cursorScreenPoint: () => cursor,
    openLocalAttachment: () => undefined,
  });

  await controller.show();
  await new Promise((resolve) => setImmediate(resolve));
  saveCount = 0;
  try {
    controller.beginDrag(72, 104);
    assert.deepEqual(window.getPosition(), [460, 460]);
    cursor = { x: 582, y: 564 };
    controller.moveDrag(cursor);
    assert.deepEqual(window.getPosition(), [510, 460]);
    assert.equal(saveCount, 0);
    controller.endDrag();

    assert.equal(saveCount, 1);
    assert.deepEqual(settings.positions["role-1:display-1"], { x: 510, y: 460 });
  } finally {
    window.destroy();
  }
});

test("desktop pet ignores drag requests from a closed window", async () => {
  let settings: DesktopPetSettings = { visible: false, roleId: null, packageId: null, positions: {} };
  const window = new FakePetWindow();
  const controller = new DesktopPetController({
    getSettings: () => settings,
    saveSettings: async (nextSettings) => {
      settings = nextSettings;
    },
    resolveBinding: async () => ({
      roleId: "role-1",
      package: { id: "pet-1", displayName: "Pet", spritesheetUrl: "mira-asset://pet" },
    }),
    createWindow: () => window as unknown as BrowserWindow,
    displayForWindow: () => ({ id: "display-1", workArea: { x: 0, y: 0, width: 1920, height: 1080 } }),
    cursorScreenPoint: () => ({ x: 532, y: 564 }),
    openLocalAttachment: () => undefined,
  });

  await controller.show();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(controller.isPetWindow(window as unknown as BrowserWindow), true);
  controller.beginDrag(72, 104);
  window.destroy();
  assert.equal(controller.isPetWindow(window as unknown as BrowserWindow), false);
});

test("desktop pet keeps its fixed viewport bounds while following a drag", async () => {
  let settings: DesktopPetSettings = { visible: false, roleId: null, packageId: null, positions: {} };
  const window = new FakePetWindow();
  const controller = new DesktopPetController({
    getSettings: () => settings,
    saveSettings: async (nextSettings) => { settings = nextSettings; },
    resolveBinding: async () => ({
      roleId: "role-1",
      package: { id: "pet-1", displayName: "Pet", spritesheetUrl: "mira-asset://pet" },
    }),
    createWindow: () => window as unknown as BrowserWindow,
    displayForWindow: () => ({ id: "display-1", workArea: { x: 0, y: 0, width: 1920, height: 1080 } }),
    cursorScreenPoint: () => ({ x: 532, y: 564 }),
    openLocalAttachment: () => undefined,
  });

  await controller.show();
  window.boundsWrites.length = 0;
  try {
    controller.beginDrag(72, 104, 532, 564);
    controller.moveDrag({ x: 582, y: 614 });
    assert.deepEqual(window.boundsWrites.at(-1), { x: 510, y: 510, width: 192, height: 208 });
  } finally {
    window.destroy();
  }
});

test("desktop pet replays the latest observation state after its renderer becomes ready", async () => {
  let settings: DesktopPetSettings = {
    visible: false,
    roleId: "role-1",
    packageId: "pet-1",
    positions: {},
  };
  const window = new FakePetWindow();
  const controller = new DesktopPetController({
    getSettings: () => settings,
    saveSettings: async (nextSettings) => { settings = nextSettings; },
    resolveBinding: async () => ({
      roleId: "role-1",
      package: { id: "pet-1", displayName: "Pet", spritesheetUrl: "mira-asset://pet" },
    }),
    createWindow: () => window as unknown as BrowserWindow,
    displayForWindow: () => ({ id: "display-1", workArea: { x: 0, y: 0, width: 1920, height: 1080 } }),
    cursorScreenPoint: () => ({ x: 0, y: 0 }),
    openLocalAttachment: () => undefined,
  });
  controller.publishObservation({
    status: "paused",
    enabled: true,
    bubble: "屏幕观察已暂停",
    persistent: true,
  });

  await controller.show();
  controller.rendererReady(window as unknown as BrowserWindow);

  const observation = window.webContents.messages.find(
    (message) => message.channel === "desktop:pet-observation",
  );
  assert.deepEqual(observation?.payload, {
    status: "paused",
    enabled: true,
    bubble: "屏幕观察已暂停",
    persistent: true,
  });
  window.destroy();
});

test("desktop pet waits for the renderer handshake before sending its initial load", async () => {
  let settings: DesktopPetSettings = {
    visible: true,
    roleId: "role-1",
    packageId: "pet-1",
    positions: {},
  };
  const window = new FakePetWindow();
  const controller = new DesktopPetController({
    getSettings: () => settings,
    saveSettings: async (nextSettings) => { settings = nextSettings; },
    resolveBinding: async () => ({
      roleId: "role-1",
      package: { id: "pet-1", displayName: "Pet", spritesheetUrl: "mira-asset://pet" },
    }),
    createWindow: () => window as unknown as BrowserWindow,
    displayForWindow: () => ({ id: "display-1", workArea: { x: 0, y: 0, width: 1920, height: 1080 } }),
    cursorScreenPoint: () => ({ x: 0, y: 0 }),
    openLocalAttachment: () => undefined,
  });

  await controller.restore();
  window.emit("ready-to-show");
  assert.equal(window.webContents.messages.some((message) => message.channel === "desktop:pet-load"), false);

  assert.equal(controller.rendererReady(window as unknown as BrowserWindow), true);
  assert.equal(window.showCount, 1);
  assert.deepEqual(
    window.webContents.messages.find((message) => message.channel === "desktop:pet-load")?.payload,
    {
      package: { id: "pet-1", displayName: "Pet", spritesheetUrl: "mira-asset://pet" },
      state: "idle",
    },
  );
  window.destroy();
});

test("changing the package for one role invalidates the active pet binding", async () => {
  let packageId = "pet-1";
  let settings: DesktopPetSettings = {
    visible: false,
    roleId: "role-1",
    packageId,
    positions: {},
  };
  const window = new FakePetWindow();
  const controller = new DesktopPetController({
    getSettings: () => settings,
    saveSettings: async (nextSettings) => { settings = nextSettings; },
    resolveBinding: async () => ({
      roleId: "role-1",
      package: { id: packageId, displayName: "Pet", spritesheetUrl: `mira-asset://${packageId}` },
    }),
    createWindow: () => window as unknown as BrowserWindow,
    displayForWindow: () => ({ id: "display-1", workArea: { x: 0, y: 0, width: 1920, height: 1080 } }),
    cursorScreenPoint: () => ({ x: 0, y: 0 }),
    openLocalAttachment: () => undefined,
  });

  await controller.show();
  controller.rendererReady(window as unknown as BrowserWindow);
  packageId = "pet-2";
  await controller.sync(true);

  assert.equal(
    window.webContents.messages.filter((message) => message.channel === "desktop:pet-load").length,
    2,
  );
  window.destroy();
});
