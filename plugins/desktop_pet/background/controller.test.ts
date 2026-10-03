import assert from "node:assert/strict";
import test from "node:test";
import type { PluginBackgroundSettled, SurfaceInteractionTarget } from "@yinfengwindy/shiori-sdk";
import { deferred } from "@yinfengwindy/shiori-sdk/testing";
import { DesktopPetController, desktopPetSurfaceId, desktopPetAgentMoveDurationMs, type DesktopPetSurfaces } from "./controller";
import { desktopPetBody, type DesktopPetBinding, type DesktopPetSettings } from "./types";

const workArea = { x: 0, y: 0, width: 1920, height: 1080 };
const binding: DesktopPetBinding = {
  roleId: "role-1",
  package: { id: "pet-1", displayName: "Pet", spritesheetUrl: "shiori-asset://local/pet-1" },
  actions: { greeting: "waving" },
};

function harness(initial: Partial<DesktopPetSettings> = {}) {
  const creates: Parameters<DesktopPetSurfaces["create"]>[] = [];
  const positions: Parameters<DesktopPetSurfaces["setPosition"]>[] = [];
  const moves: Parameters<DesktopPetSurfaces["moveTo"]>[] = [];
  const posts: unknown[] = [];
  const states: unknown[] = [];
  const targets: (SurfaceInteractionTarget | null)[] = [];
  const destroyed: string[] = [];
  const saves: DesktopPetSettings[] = [];
  const errors: string[] = [];
  let nextBinding: DesktopPetBinding | null = binding;
  let createGate: Promise<void> = Promise.resolve();
  let bindingGate: Promise<void> = Promise.resolve();
  let areaGate: Promise<void> = Promise.resolve();
  let saveGate: Promise<void> = Promise.resolve();
  const surfaces: DesktopPetSurfaces = {
    create: async (...args) => { creates.push(args); await createGate; return { x: 100, y: 200, displayId: "display-1" }; },
    destroy: async (id) => { destroyed.push(id); },
    setPosition: (...args) => { positions.push(args); },
    moveTo: (...args) => { moves.push(args); },
    post: (_id, value) => { posts.push(value); },
    setState: (_id, value) => { states.push(value); },
    setInteraction: (_id, target) => { targets.push(target); },
    workArea: async () => { await areaGate; return workArea; },
  };
  const controller = new DesktopPetController({
    surfaces,
    settings: { visible: false, roleId: null, packageId: null, positions: {}, ...initial },
    saveSettings: async (value) => { saves.push(value); await saveGate; },
    resolveBinding: async () => { await bindingGate; return nextBinding; },
    onError: (operation) => { errors.push(operation); },
  });
  return {
    controller, creates, positions, moves, posts, states, targets, destroyed, saves, errors,
    setBinding: (value: DesktopPetBinding | null) => { nextBinding = value; },
    holdCreate: (value: Promise<void>) => { createGate = value; },
    holdBinding: (value: Promise<void>) => { bindingGate = value; },
    holdArea: (value: Promise<void>) => { areaGate = value; },
    holdSave: (value: Promise<void>) => { saveGate = value; },
  };
}

const flush = async () => { for (let step = 0; step < 8; step++) await Promise.resolve(); };
const move = { role_id: "role-1", channel: "desktop", kind: "move", target: "bottom_right", animation: "run" };
function settled(reason: PluginBackgroundSettled["reason"], x = 500): PluginBackgroundSettled {
  return { reason, displayId: "display-1", placement: { anchor: { x, y: 400 }, bodyOffset: { x: 0, y: 0 }, workArea } };
}

test("show creates the declared body, retains content and declares the role independently of persistence", async () => {
  const pet = harness();
  await pet.controller.show();
  assert.deepEqual(pet.creates, [[desktopPetSurfaceId, { body: desktopPetBody }, { x: Number.MAX_SAFE_INTEGER, y: Number.MAX_SAFE_INTEGER }]]);
  assert.deepEqual(pet.states, [{ load: { package: binding.package, state: "idle" }, reply: { text: "", paused: false, persistent: false } }]);
  assert.deepEqual(pet.targets.at(-1), { roleId: "role-1", available: true });
  assert.equal(pet.controller.isRunning, true);
});

test("a reply arriving during create remains retained after restore", async () => {
  const pet = harness();
  const gate = deferred<void>();
  pet.holdCreate(gate.promise);
  const showing = pet.controller.show();
  await flush();
  pet.controller.replies.handleEvent({ id: "reply", type: "event", method: "chat.done", payload: { role_id: "role-1", reply: "正在启动时的回复" } });
  gate.resolve();
  await showing;
  await pet.controller.restore();
  assert.deepEqual(pet.states.at(-1), { load: { package: binding.package, state: "idle" }, reply: { text: "正在启动时的回复", paused: false, persistent: false } });
  await pet.controller.terminate();
});

test("disable during create destroys the eventual window without declaring or saving visible state", async () => {
  const pet = harness();
  const gate = deferred<void>();
  pet.holdCreate(gate.promise);
  const showing = pet.controller.show();
  await flush();
  const stopping = pet.controller.terminate();
  gate.resolve();
  await Promise.all([showing, stopping]);
  assert.deepEqual(pet.destroyed, [desktopPetSurfaceId]);
  assert.deepEqual(pet.targets, []);
  assert.deepEqual(pet.states, []);
  assert.deepEqual(pet.saves, []);
});

test("reply updates retain the package alongside the bubble", async () => {
  const pet = harness();
  await pet.controller.show();
  pet.controller.replies.setLocked(true);
  assert.deepEqual(pet.states.at(-1), { load: { package: binding.package, state: "idle" }, reply: { text: "Windows 已锁定", paused: true, persistent: true } });
  await pet.controller.terminate();
});

test("restore applies only the remembered position for the returned display", async () => {
  for (const display of ["display-1", "display-other"]) {
    const pet = harness({ visible: true, roleId: "role-1", packageId: "pet-1", positions: { [`role-1:${display}`]: { x: 510, y: 800 } } });
    await pet.controller.restore();
    assert.deepEqual(pet.positions, display === "display-1" ? [[desktopPetSurfaceId, { x: 510, y: 800 }]] : []);
  }
});

test("only drag, momentum and requested move settlements persist positions", async () => {
  const pet = harness();
  await pet.controller.show();
  pet.saves.length = 0;
  for (const reason of ["create", "position", "extension", "ready"] as const) pet.controller.handleSettled(settled(reason));
  assert.equal(pet.saves.length, 0);
  for (const reason of ["drag", "momentum", "move"] as const) pet.controller.handleSettled(settled(reason));
  assert.equal(pet.saves.length, 3);
  assert.deepEqual(pet.saves.at(-1)?.positions["role-1:display-1"], { x: 500, y: 400 });
});

test("hide immediately revokes interaction and then destroys the surface", async () => {
  const pet = harness();
  await pet.controller.show();
  const hiding = pet.controller.hide();
  assert.equal(pet.targets.at(-1), null);
  await hiding;
  assert.deepEqual(pet.destroyed, [desktopPetSurfaceId]);
  assert.equal(pet.controller.isRunning, false);
  assert.equal(pet.controller.currentSettings.visible, false);
});

test("new hide intent retires an older binding read without re-admitting or saving visible state", async () => {
  for (const hideViaSync of [false, true]) {
    const pet = harness();
    await pet.controller.show();
    pet.saves.length = 0;
    const bindingReady = deferred<void>();
    const saveReady = deferred<void>();
    pet.holdBinding(bindingReady.promise);
    pet.holdSave(saveReady.promise);
    const syncing = pet.controller.sync();
    await flush();
    const hiding = hideViaSync ? pet.controller.sync(false) : pet.controller.hide();
    assert.equal(pet.targets.at(-1), null);
    const afterHide = pet.targets.length;
    bindingReady.resolve();
    await flush();
    assert.ok(pet.targets.slice(afterHide).every((target) => target === null));
    assert.deepEqual(pet.saves.map((settings) => settings.visible), [false]);
    const showingAgain = pet.controller.show();
    await flush();
    assert.ok(pet.targets.slice(afterHide).every((target) => target === null));
    saveReady.resolve();
    await Promise.all([syncing, hiding, showingAgain]);
    assert.deepEqual(pet.targets.at(-1), { roleId: "role-1", available: true });
    assert.equal(pet.controller.currentSettings.visible, true);
  }
});

test("hide during create never publishes the obsolete show and a later show still works", async () => {
  const pet = harness();
  const created = deferred<void>();
  pet.holdCreate(created.promise);
  const showing = pet.controller.show();
  await flush();
  const hiding = pet.controller.hide();
  created.resolve();
  await Promise.all([showing, hiding]);
  assert.deepEqual(pet.targets, []);
  assert.deepEqual(pet.states, []);
  assert.deepEqual(pet.saves.map((settings) => settings.visible), [false]);
  assert.deepEqual(pet.destroyed, [desktopPetSurfaceId]);
  await pet.controller.show();
  assert.equal(pet.creates.length, 2);
  assert.deepEqual(pet.targets.at(-1), { roleId: "role-1", available: true });
});

test("hide retires already queued show requests before they open a window", async () => {
  const pet = harness();
  const showing = pet.controller.show();
  const hiding = pet.controller.hide();
  await Promise.all([showing, hiding]);
  assert.deepEqual(pet.creates, []);
  assert.deepEqual(pet.targets, []);
  assert.deepEqual(pet.saves.map((settings) => settings.visible), [false]);
});

test("forced hide still refreshes role-save binding metadata after reclaiming the window", async () => {
  const pet = harness();
  await pet.controller.show();
  const bindingReady = deferred<void>();
  pet.holdBinding(bindingReady.promise);
  pet.setBinding(null);
  const hiding = pet.controller.sync(false);
  await flush();
  assert.deepEqual(pet.destroyed, [desktopPetSurfaceId]);
  assert.equal(pet.targets.at(-1), null);
  bindingReady.resolve();
  await hiding;
  assert.equal(pet.controller.currentSettings.visible, false);
  assert.equal(pet.controller.currentSettings.roleId, null);
  assert.equal(pet.controller.currentSettings.packageId, null);
});

test("disable destroys a running surface and a pending binding never opens one", async () => {
  const pet = harness();
  await pet.controller.show();
  await pet.controller.terminate();
  assert.deepEqual(pet.destroyed, [desktopPetSurfaceId]);
  const pending = harness();
  const gate = deferred<void>();
  pending.holdBinding(gate.promise);
  const showing = pending.controller.show();
  const stopping = pending.controller.terminate();
  gate.resolve();
  await Promise.all([showing, stopping]);
  assert.deepEqual(pending.creates, []);
  assert.deepEqual(pending.targets, []);
});

test("rebinding reuses the window and replaces its role target", async () => {
  const pet = harness();
  await pet.controller.show();
  const replacement = { ...binding, roleId: "role-2", package: { ...binding.package, id: "pet-2" } };
  pet.setBinding(replacement);
  await pet.controller.sync(true);
  assert.equal(pet.creates.length, 1);
  assert.deepEqual(pet.states.at(-1), { load: { package: replacement.package, state: "idle" }, reply: { text: "", paused: false, persistent: false } });
  assert.deepEqual(pet.targets.slice(-2), [null, { roleId: "role-2", available: true }]);
});

test("a missing binding destroys the surface and clears saved selection", async () => {
  const pet = harness();
  await pet.controller.show();
  pet.setBinding(null);
  await pet.controller.sync();
  assert.equal(pet.controller.isRunning, false);
  assert.equal(pet.controller.currentSettings.roleId, null);
  assert.equal(pet.controller.currentSettings.packageId, null);
  assert.equal(pet.controller.currentSettings.visible, false);
  assert.equal(pet.targets.at(-1), null);
});

test("declared play actions are transient and never replace retained animation state", async () => {
  const pet = harness();
  await pet.controller.show();
  const previous = pet.states.at(-1);
  pet.controller.handleAgentAction({ ...move, kind: "play", name: "greeting" });
  assert.deepEqual(pet.posts, [{ state: "waving", transient: true }]);
  assert.equal(pet.states.at(-1), previous);
});

test("agent corner and centre moves delegate animation to the host and persist only the landing", async () => {
  const pet = harness();
  await pet.controller.show();
  pet.saves.length = 0;
  pet.controller.handleAgentAction(move);
  await flush();
  assert.deepEqual(pet.moves, [[desktopPetSurfaceId, { x: 1920, y: 1080 }, desktopPetAgentMoveDurationMs]]);
  assert.deepEqual(pet.posts, [{ state: "running-right", transient: true }]);
  assert.equal(pet.saves.length, 0);
  pet.controller.handleSettled(settled("move"));
  assert.equal(pet.saves.length, 1);
  pet.controller.handleAgentAction({ ...move, target: "center" });
  await flush();
  assert.deepEqual(pet.moves.at(-1), [desktopPetSurfaceId, { x: (1920 - desktopPetBody.width) / 2, y: (1080 - desktopPetBody.height) / 2 }, desktopPetAgentMoveDurationMs]);
});

test("foreign role and stopped-surface actions are ignored", async () => {
  const pet = harness();
  pet.controller.handleAgentAction(move);
  await pet.controller.show();
  pet.controller.handleAgentAction({ ...move, role_id: "other" });
  await flush();
  assert.deepEqual(pet.moves, []);
});

test("work-area replies cannot move a hidden or rebound target", async () => {
  for (const change of ["hide", "rebind"] as const) {
    const pet = harness();
    await pet.controller.show();
    const gate = deferred<void>();
    pet.holdArea(gate.promise);
    pet.controller.handleAgentAction(move);
    if (change === "hide") await pet.controller.hide();
    else { pet.setBinding({ ...binding, roleId: "role-2" }); await pet.controller.sync(); }
    gate.resolve();
    await flush();
    assert.deepEqual(pet.moves, []);
    assert.deepEqual(pet.errors, []);
  }
});
