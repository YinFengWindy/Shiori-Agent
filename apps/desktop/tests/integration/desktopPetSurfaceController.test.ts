import assert from "node:assert/strict";
import test from "node:test";
import { deferred } from "@shiori/sdk/testing";
import { DesktopSurfaceHost, surfaceStateChannel, type SurfaceWindowHandle } from "../../src/surface/host";
import { DesktopVoiceController } from "../../src/voice/controller";
import { SurfaceVoiceController } from "../../src/voice/surfaceVoice";
import { DesktopPetController, desktopPetSurfaceId, type DesktopPetSurfaces } from "../../../../plugins/desktop_pet/background/controller";

/** Actual owners assembled through public capabilities; no pet KV reader participates. */
function harness() {
  const key = { pluginId: "desktop_pet", surfaceId: desktopPetSurfaceId };
  const sent: { channel: string; payload: unknown }[] = [];
  let destroyed = false;
  let closed = () => {};
  let bounds = { x: 0, y: 0, width: 0, height: 0 };
  let shown = 0;
  const window: SurfaceWindowHandle = {
    id: 47, setBounds: (value) => { bounds = value; }, getBounds: () => bounds,
    isDestroyed: () => destroyed, destroy: () => { destroyed = true; closed(); },
    showInactive: () => { shown++; }, hide() {}, setIgnoreMouseEvents() {},
    send: (channel, payload) => { sent.push({ channel, payload }); },
    onClosed: (listener) => { closed = listener; },
  };
  const host = new DesktopSurfaceHost({
    createWindow: () => window,
    workAreaFor: () => ({ x: 0, y: 0, width: 1920, height: 1080 }),
    cursorScreenPoint: () => ({ x: 0, y: 0 }),
    onInteractionChanged: () => surfaceVoice?.revalidate(),
  });
  const surfaces: DesktopPetSurfaces = {
    create: async (_id, spec, anchor) => ({ ...host.create(key, spec, anchor), displayId: "display" }),
    destroy: async () => host.destroy(key),
    setInteraction: (_id, target) => host.setInteraction(key, target),
    setState: (_id, state) => host.setState(key, state),
    setPosition: (_id, position) => { host.setPosition(key, position); },
    moveTo: (_id, position, duration) => host.moveTo(key, position, duration),
    post: (_id, value) => host.postMessage(key, value),
    workArea: async () => host.workArea(key),
  };
  let roleId = "role-a";
  const pet = new DesktopPetController({
    surfaces, settings: { visible: false, roleId: null, packageId: null, positions: {} },
    saveSettings: async () => {},
    resolveBinding: async () => ({ roleId, package: { id: "pet", displayName: "Pet", spritesheetUrl: "asset://pet" } }),
  });
  const asr = deferred<{ text: string }>();
  const requests: string[] = [];
  let now = 0;
  const timers = new Map<ReturnType<typeof setTimeout>, { callback: () => void; delay: number }>();
  const voice = new DesktopVoiceController({
    recorder: { start: async () => {}, stop: async () => new Uint8Array([1]), cancel: async () => {} },
    isEnabled: () => host.interactionTargets().length > 0,
    roleId: () => host.interactionTargets()[0]?.roleId ?? null,
    publishState: (state) => surfaceVoice?.publish(state),
    now: () => now,
    schedule: (callback, delay) => {
      const timer = setTimeout(() => {}, 60_000);
      timers.set(timer, { callback, delay });
      return timer;
    },
    clearSchedule: (timer) => { clearTimeout(timer); timers.delete(timer); },
    bridge: { invoke: async (request) => {
      requests.push(request.method);
      return { id: "reply", type: "response", method: request.method, payload: request.method === "voice.transcribe" ? await asr.promise : {}, error: null };
    } },
  });
  const surfaceVoice = new SurfaceVoiceController(host, voice);
  const advancePress = () => {
    for (const [timer, entry] of timers) {
      if (entry.delay !== 300) continue;
      clearTimeout(timer);
      timers.delete(timer);
      now += entry.delay;
      entry.callback();
    }
  };
  return { key, host, pet, voice, surfaceVoice, sent, requests, asr, advancePress, shown: () => shown, setRole: (id: string) => { roleId = id; } };
}

const tick = () => new Promise<void>((resolve) => setImmediate(resolve));

test("public pet declaration admits its actual ready window and hide cancels its voice turn", async () => {
  const h = harness();
  try {
    await h.pet.show();
    assert.deepEqual(h.host.interactionTargets(), []);
    assert.equal(h.surfaceVoice.startPress(47), false);
    assert.equal(h.shown(), 0);
    h.host.markReady(h.key);
    assert.equal(h.shown(), 1);
    assert.equal(h.sent.filter((item) => item.channel === surfaceStateChannel).length, 2);
    assert.equal(h.surfaceVoice.startPress(999), false);
    assert.equal(h.surfaceVoice.startPress(47), true);
    h.advancePress();
    await tick();
    assert.equal(h.voice.currentState.kind, "recording");
    const hiding = h.pet.hide();
    assert.equal(h.voice.currentState.kind, "idle");
    await hiding;
    assert.deepEqual(h.host.interactionTargets(), []);
  } finally { h.voice.dispose(); await h.pet.terminate(); }
});

test("a role change during ASR cannot submit the old speech to the replacement role", async () => {
  const h = harness();
  try {
    await h.pet.show();
    h.host.markReady(h.key);
    h.surfaceVoice.startPress(47);
    h.advancePress();
    await tick();
    h.surfaceVoice.gesture(47, "release");
    await tick();
    assert.deepEqual(h.requests, ["voice.transcribe"]);
    h.setRole("role-b");
    await h.pet.sync();
    assert.equal(h.voice.currentState.kind, "idle");
    assert.equal(h.host.interactionTargets()[0]?.roleId, "role-b");
    h.asr.resolve({ text: "old speech" });
    await tick();
    assert.deepEqual(h.requests, ["voice.transcribe"]);
  } finally { h.voice.dispose(); await h.pet.terminate(); }
});
