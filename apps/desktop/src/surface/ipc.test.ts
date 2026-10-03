import assert from "node:assert/strict";
import { test } from "node:test";
import type { SurfaceSpec } from "@yinfengwindy/shiori-sdk/contract";
import { DesktopSurfaceHost, type SurfaceWindowHandle } from "./host.js";
import { registerSurfaceIpc, surfaceChannels, type SurfaceIpcEvent } from "./ipc.js";

const body = { width: 100, height: 100 };
const spec: SurfaceSpec = { body };
const workArea = { x: 0, y: 0, width: 1000, height: 1000 };

class FakeWindow implements SurfaceWindowHandle {
  static nextId = 500;
  readonly id = FakeWindow.nextId++;
  bounds = { x: 0, y: 0, width: body.width, height: body.height };
  destroyed = false;
  setBounds(bounds: typeof this.bounds) { this.bounds = bounds; }
  getBounds() { return this.bounds; }
  isDestroyed() { return this.destroyed; }
  destroy() { this.destroyed = true; }
  showInactive() {}
  hide() {}
  setIgnoreMouseEvents() {}
  send() {}
  onClosed() {}
}

/** Collects registrations so a test can invoke a channel the way Electron would. */
class FakeIpc {
  readonly handlers = new Map<string, (event: SurfaceIpcEvent, payload: unknown) => unknown>();
  readonly listeners = new Map<string, (event: SurfaceIpcEvent, payload: unknown) => void>();
  windowId: number | null = null;

  handle(channel: string, listener: (event: SurfaceIpcEvent, payload: unknown) => unknown) {
    this.handlers.set(channel, listener);
  }
  on(channel: string, listener: (event: SurfaceIpcEvent, payload: unknown) => void) {
    this.listeners.set(channel, listener);
  }
  windowIdFromEvent() { return this.windowId; }

  invoke(channel: string, payload: unknown) {
    const handler = this.handlers.get(channel);
    assert.ok(handler, `no handler registered for ${channel}`);
    return handler({ sender: null }, payload);
  }
  send(channel: string, payload: unknown) {
    const listener = this.listeners.get(channel);
    assert.ok(listener, `no listener registered for ${channel}`);
    listener({ sender: null }, payload);
  }
}

function setup() {
  const windows: FakeWindow[] = [];
  const errors: { channel: string; error: unknown }[] = [];
  const surfaces = new DesktopSurfaceHost({
    createWindow: () => { const window = new FakeWindow(); windows.push(window); return window; },
    workAreaFor: () => workArea,
    displayIdFor: (window) => `display-${window.id}`,
    cursorScreenPoint: () => ({ x: 0, y: 0 }),
  });
  const ipc = new FakeIpc();
  registerSurfaceIpc(ipc, { surfaces, onError: (channel, error) => errors.push({ channel, error }) });
  return { ipc, surfaces, windows, errors };
}

const key = { pluginId: "demo", surfaceId: "main" };

test("create places the surface and reports the clamped anchor back to the caller", () => {
  const { ipc, surfaces, windows } = setup();
  const applied = ipc.invoke(surfaceChannels.create, { ...key, spec, x: -20, y: 40 });
  // The display comes back with the anchor rather than on a second call: a
  // plugin that remembers a per-display position has to apply it before the
  // window paints, and a round trip would show the fallback corner first.
  assert.deepEqual(applied, { x: 0, y: 40, displayId: `display-${windows[0].id}` });
  assert.equal(surfaces.has(key), true);
  assert.deepEqual(windows[0].bounds, { x: 0, y: 40, width: 100, height: 100 });
});

test("a malformed create request is refused instead of creating a broken window", () => {
  const { ipc, windows } = setup();
  for (const payload of [
    null,
    { surfaceId: "main", spec },
    { ...key },
    { ...key, spec: { body: { width: 0, height: 10 } } },
    { ...key, spec: { body: { width: Number.NaN, height: 10 } } },
  ]) {
    assert.throws(() => ipc.invoke(surfaceChannels.create, payload));
  }
  assert.equal(windows.length, 0);
});

test("a surface renderer drives the window it is inside without naming it", () => {
  const { ipc, windows } = setup();
  ipc.invoke(surfaceChannels.create, { ...key, spec, x: 300, y: 300 });
  ipc.windowId = windows[0].id;

  ipc.send(surfaceChannels.setExtension, { side: "above", size: 40 });
  assert.deepEqual(windows[0].bounds, { x: 300, y: 260, width: 100, height: 140 });
});

test("a renderer with no surface of its own is ignored, not obeyed", () => {
  const { ipc, windows } = setup();
  ipc.invoke(surfaceChannels.create, { ...key, spec, x: 300, y: 300 });
  const before = { ...windows[0].bounds };
  ipc.windowId = 99_999;

  ipc.send(surfaceChannels.setExtension, { side: "above", size: 40 });
  ipc.send(surfaceChannels.beginDrag, { offsetX: 0, offsetY: 0 });
  ipc.send(surfaceChannels.setClickThrough, { clickThrough: true });

  assert.deepEqual(windows[0].bounds, before);
});

test("NaN and missing coordinates never reach window bounds", () => {
  const { ipc, windows } = setup();
  ipc.invoke(surfaceChannels.create, { ...key, spec, x: 300, y: 300 });
  const before = { ...windows[0].bounds };

  ipc.send(surfaceChannels.setPosition, { ...key, x: Number.NaN, y: 10 });
  ipc.send(surfaceChannels.setPosition, { ...key, x: "40", y: 10 });
  ipc.send(surfaceChannels.setPosition, { ...key });
  ipc.send(surfaceChannels.setExtension, { side: "sideways", size: 10 });

  assert.deepEqual(windows[0].bounds, before);
});

test("a request for a surface that is already gone is reported, not thrown at the caller", () => {
  const { ipc, errors } = setup();
  ipc.send(surfaceChannels.setPosition, { ...key, x: 10, y: 10 });
  assert.equal(errors.length, 1);
  assert.equal(errors[0].channel, surfaceChannels.setPosition);
});

test("destroying an unknown surface is a silent no-op", () => {
  const { ipc, errors } = setup();
  ipc.invoke(surfaceChannels.destroy, { ...key });
  assert.deepEqual(errors, []);
});

test("work area is reported for a named surface and refused for an unknown one", () => {
  const { ipc } = setup();
  ipc.invoke(surfaceChannels.create, { ...key, spec, x: 0, y: 0 });
  assert.deepEqual(ipc.invoke(surfaceChannels.workArea, { ...key }), workArea);
  assert.throws(() => ipc.invoke(surfaceChannels.workArea, { pluginId: "demo" }));
});


test("interaction declarations are explicit, validated and revoked independently of retained data", () => {
  const { ipc, surfaces, windows } = setup();
  ipc.invoke(surfaceChannels.create, { ...key, spec });
  ipc.windowId = windows[0].id;
  ipc.send(surfaceChannels.ready, {});
  for (const target of [{ roleId: "", available: true }, { roleId: "a", available: "yes" }, { visible: true, roleId: "a", packageId: "pet" }]) {
    ipc.send(surfaceChannels.setInteraction, { ...key, target });
    assert.deepEqual(surfaces.interactionTargets(), []);
  }
  ipc.send(surfaceChannels.setInteraction, { ...key, target: { roleId: "a", available: true } });
  assert.equal(surfaces.interactionTargets()[0]?.roleId, "a");
  ipc.send(surfaceChannels.setInteraction, { ...key, target: null });
  assert.deepEqual(surfaces.interactionTargets(), []);
});
