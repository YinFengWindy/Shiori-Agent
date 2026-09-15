import assert from "node:assert/strict";
import test from "node:test";
import {
  DesktopSurfaceHost,
  surfaceMessageChannel,
  surfacePositionChannel,
  surfaceStateChannel,
  type SurfaceWindowHandle,
} from "../../../apps/desktop/src/surface/host";
import {
  DesktopPetController,
  desktopPetAgentMoveDurationMs,
  desktopPetSurfaceId,
  type DesktopPetSurfaces,
} from "./controller";
import { desktopPetBody, type DesktopPetSettings } from "./types";

/**
 * These tests drive the *real* `DesktopSurfaceHost` over fake window handles
 * rather than a stubbed-out surface capability.
 *
 * The controller contains no geometry: clamping, the bubble extension and the
 * release glide all live in the host, so a fully faked surface would assert
 * only that the controller calls methods — not that the pet ends up where it
 * should. The window handle is the lowest seam that still exercises the
 * arithmetic.
 *
 * What the fake *does* stand in for is the IPC hop: `ctx.surfaces` answers
 * asynchronously, and `create` carries the display id back with the anchor.
 * Ported from `apps/desktop/src/pet/controller.test.ts`, which #181-C deleted
 * along with the main-process controller it covered.
 */

const workArea = { x: 0, y: 0, width: 1920, height: 1080 };
const surfaceKey = { pluginId: "desktop_pet", surfaceId: desktopPetSurfaceId };

let nextWindowId = 1;

class FakeSurfaceWindow implements SurfaceWindowHandle {
  readonly id = nextWindowId++;
  readonly boundsWrites: { x: number; y: number; width: number; height: number }[] = [];
  readonly messages: { channel: string; payload: unknown }[] = [];
  showCount = 0;
  hideCount = 0;
  private destroyed = false;
  private closedListener: (() => void) | null = null;
  private bounds = { x: 0, y: 0, width: desktopPetBody.width, height: desktopPetBody.height };

  setBounds(bounds: { x: number; y: number; width: number; height: number }): void {
    this.bounds = bounds;
    this.boundsWrites.push(bounds);
  }

  getBounds() {
    return { ...this.bounds };
  }

  isDestroyed(): boolean {
    return this.destroyed;
  }

  destroy(): void {
    this.destroyed = true;
    this.closedListener?.();
  }

  showInactive(): void {
    this.showCount += 1;
  }

  hide(): void {
    this.hideCount += 1;
  }

  setIgnoreMouseEvents(): void {}

  send(channel: string, payload: unknown): void {
    this.messages.push({ channel, payload });
  }

  onClosed(listener: () => void): void {
    this.closedListener = listener;
  }

  /** Payloads sent on one channel, oldest first. */
  payloads(channel: string): unknown[] {
    return this.messages.filter((message) => message.channel === channel).map((message) => message.payload);
  }
}

type Harness = {
  controller: DesktopPetController;
  surfaces: DesktopSurfaceHost;
  windows: FakeSurfaceWindow[];
  window: () => FakeSurfaceWindow;
  settings: () => DesktopPetSettings;
  saveCount: () => number;
  resetSaveCount: () => void;
  setPackageId: (id: string) => void;
  setBinding: (present: boolean) => void;
  advance: (ms: number) => void;
  /** Failures the controller reported from a path with no caller to throw at. */
  errors: () => string[];
  /**
   * Holds the next `workArea` answer, then delivers it on demand.
   *
   * `ctx.surfaces.workArea` is an IPC round trip in production, and the pet can
   * be switched off inside it. Without a gate the fake answers on the next
   * microtask, which lands *before* a `hide()` in the same test finishes — so
   * the race the controller guards against would never actually occur.
   */
  holdWorkArea: () => void;
  releaseWorkArea: () => void;
  /** Holds the next `binding.get` answer, then delivers it on demand. */
  holdBinding: () => void;
  releaseBinding: () => void;
  /** Lets the controller's own promise chain drain, standing in for the IPC hop. */
  flush: () => Promise<void>;
};

/**
 * Builds a controller wired to a real surface host with an injected clock, so
 * the release glide and the eased agent move run deterministically.
 */
function harness(initialSettings?: Partial<DesktopPetSettings>, actions?: Record<string, "waving">, createGate?: Promise<void>): Harness {
  let settings: DesktopPetSettings = {
    visible: false,
    roleId: null,
    packageId: null,
    positions: {},
    ...initialSettings,
  };
  let saveCount = 0;
  let packageId = "pet-1";
  let hasBinding = true;
  let holdingWorkArea = false;
  let heldWorkArea: (() => void) | null = null;
  let holdingBinding = false;
  let heldBinding: (() => void) | null = null;
  const errors: string[] = [];
  const windows: FakeSurfaceWindow[] = [];

  let now = 0;
  const timers: { id: number; at: number; callback: () => void }[] = [];
  let nextTimerId = 1;

  const surfaces = new DesktopSurfaceHost({
    createWindow: () => {
      const window = new FakeSurfaceWindow();
      windows.push(window);
      return window;
    },
    workAreaFor: () => workArea,
    displayIdFor: () => "display-1",
    cursorScreenPoint: () => ({ x: 0, y: 0 }),
    now: () => now,
    setTimer: (callback, delayMs) => {
      const id = nextTimerId++;
      timers.push({ id, at: now + delayMs, callback });
      return id as unknown as ReturnType<typeof setTimeout>;
    },
    clearTimer: (handle) => {
      const index = timers.findIndex((timer) => timer.id === (handle as unknown as number));
      if (index >= 0) timers.splice(index, 1);
    },
    onSettled: (key, placement, reason) => {
      if (key.pluginId !== surfaceKey.pluginId || key.surfaceId !== surfaceKey.surfaceId) return;
      controller.handleSettled({ placement, reason, displayId: surfaces.displayId(key) });
    },
  });

  /** The `ctx.surfaces` slice, bound to this plugin id the way the real ctx is. */
  const petSurfaces: DesktopPetSurfaces = {
    create: (surfaceId, spec, anchor) => {
      const applied = surfaces.create({ ...surfaceKey, surfaceId }, spec, anchor);
      const result = { ...applied, displayId: surfaces.displayId({ ...surfaceKey, surfaceId }) };
      return createGate ? createGate.then(() => result) : Promise.resolve(result);
    },
    destroy: (surfaceId) => {
      surfaces.destroy({ ...surfaceKey, surfaceId });
      return Promise.resolve();
    },
    setPosition: (surfaceId, position) => { surfaces.setPosition({ ...surfaceKey, surfaceId }, position); },
    moveTo: (surfaceId, position, durationMs) => { surfaces.moveTo({ ...surfaceKey, surfaceId }, position, durationMs); },
    post: (surfaceId, message) => { surfaces.postMessage({ ...surfaceKey, surfaceId }, message); },
    setState: (surfaceId, state) => { surfaces.setState({ ...surfaceKey, surfaceId }, state); },
    workArea: (surfaceId) => {
      // Read now, delivered later: the host computes the work area while the
      // surface still exists, and the answer crosses the boundary afterwards.
      const value = surfaces.workArea({ ...surfaceKey, surfaceId });
      if (!holdingWorkArea) return Promise.resolve(value);
      return new Promise((resolve) => { heldWorkArea = () => resolve(value); });
    },
  };

  const controller = new DesktopPetController({
    surfaces: petSurfaces,
    settings,
    saveSettings: (next) => {
      saveCount += 1;
      settings = next;
      return Promise.resolve();
    },
    resolveBinding: () => {
      const value = hasBinding
        ? {
          roleId: "role-1",
          package: { id: packageId, displayName: "Pet", spritesheetUrl: `shiori-asset://local/${packageId}` },
          actions,
        }
        : null;
      if (!holdingBinding) return Promise.resolve(value);
      return new Promise((resolve) => { heldBinding = () => resolve(value); });
    },
    onError: (operation) => { errors.push(operation); },
  });

  return {
    controller,
    surfaces,
    windows,
    window: () => {
      const window = windows.at(-1);
      assert.ok(window, "a surface window should have been created");
      return window;
    },
    settings: () => settings,
    saveCount: () => saveCount,
    resetSaveCount: () => { saveCount = 0; },
    setPackageId: (id) => { packageId = id; },
    setBinding: (present) => { hasBinding = present; },
    errors: () => errors,
    holdWorkArea: () => { holdingWorkArea = true; },
    releaseWorkArea: () => { holdingWorkArea = false; heldWorkArea?.(); heldWorkArea = null; },
    holdBinding: () => { holdingBinding = true; },
    releaseBinding: () => { holdingBinding = false; heldBinding?.(); heldBinding = null; },
    flush: async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); },
    advance: (ms) => {
      const target = now + ms;
      for (;;) {
        const due = timers
          .filter((timer) => timer.at <= target)
          .sort((left, right) => left.at - right.at)[0];
        if (!due) break;
        timers.splice(timers.indexOf(due), 1);
        now = due.at;
        due.callback();
      }
      now = target;
    },
  };
}

test("the pet creates its surface and retains the package for a renderer that is not up yet", async () => {
  const pet = harness();

  await pet.controller.show();

  assert.equal(pet.controller.isRunning, true);
  assert.equal(pet.windows.length, 1);
  // Retained rather than fire-and-forget: the surface renderer mounts
  // asynchronously and may reload at any time.
  assert.deepEqual(pet.window().payloads(surfaceStateChannel), [{
    load: {
      package: { id: "pet-1", displayName: "Pet", spritesheetUrl: "shiori-asset://local/pet-1" },
      state: "idle",
    },
    reply: { text: "", paused: false, persistent: false },
  }]);
});

test("a reply arriving during surface creation survives readiness and restore", async () => {
  let release!: () => void;
  const pet = harness(undefined, undefined, new Promise<void>((resolve) => { release = resolve; }));
  const showing = pet.controller.show();
  await pet.flush();
  assert.equal(pet.windows.length, 1);
  pet.controller.replies.handleEvent({ id: "reply", type: "event", method: "chat.done", payload: { role_id: "role-1", reply: "正在启动时的回复" } });
  release();
  await showing;
  await pet.controller.restore();
  pet.surfaces.markReady(surfaceKey);
  const retained = pet.window().payloads(surfaceStateChannel).at(-1) as { reply: { text: string } };
  assert.equal(retained.reply.text, "正在启动时的回复");
  await pet.controller.terminate();
});

test("disable during surface creation discards replies and never saves visible state", async () => {
  let release!: () => void;
  const pet = harness(undefined, undefined, new Promise<void>((resolve) => { release = resolve; }));
  const showing = pet.controller.show();
  await pet.flush();
  const stopping = pet.controller.terminate();
  release();
  await Promise.all([showing, stopping]);
  assert.equal(pet.controller.isRunning, false);
  assert.equal(pet.saveCount(), 0);
  assert.equal(pet.window().isDestroyed(), true);
  assert.equal(pet.window().payloads(surfaceStateChannel).length, 0);
});

test("the host replays retained state and reveals the surface when the renderer reports ready", async () => {
  const pet = harness();
  await pet.controller.show();
  pet.controller.replies.setLocked(true);
  assert.equal(pet.window().showCount, 0, "an empty transparent window must not be shown");

  pet.surfaces.markReady(surfaceKey);

  assert.equal(pet.window().showCount, 1);
  const replayed = pet.window().payloads(surfaceStateChannel).at(-1) as { reply?: unknown };
  assert.deepEqual(replayed.reply, {
    paused: true,
    text: "Windows 已锁定",
    persistent: true,
  });
});

test("a reply update resends the package alongside it in one retained payload", async () => {
  const pet = harness();
  await pet.controller.show();

  pet.controller.replies.handleEvent({ id: "chat", type: "event", method: "chat.done", payload: { role_id: "role-1", reply: "继续写吧" } });

  assert.deepEqual(pet.window().payloads(surfaceStateChannel).at(-1), {
    load: {
      package: { id: "pet-1", displayName: "Pet", spritesheetUrl: "shiori-asset://local/pet-1" },
      state: "idle",
    },
    reply: { paused: false, text: "继续写吧", persistent: false },
  });
});

test("the pet restores the position remembered for the display it opened on", async () => {
  const pet = harness({
    visible: true,
    roleId: "role-1",
    packageId: "pet-1",
    positions: { "role-1:display-1": { x: 510, y: 800 } },
  });

  await pet.controller.restore();

  assert.deepEqual(pet.window().boundsWrites.at(-1), {
    x: 510,
    y: 800,
    width: desktopPetBody.width,
    height: desktopPetBody.height,
  });
});

test("a position remembered for another display is not applied to this one", async () => {
  const pet = harness({
    visible: true,
    roleId: "role-1",
    packageId: "pet-1",
    positions: { "role-1:display-9": { x: 510, y: 800 } },
  });

  await pet.controller.restore();

  // Falls back to the corner clamp, not to a coordinate from a monitor that is
  // not attached any more.
  assert.deepEqual(pet.window().boundsWrites.at(-1), {
    x: workArea.width - desktopPetBody.width,
    y: workArea.height - desktopPetBody.height,
    width: desktopPetBody.width,
    height: desktopPetBody.height,
  });
});

test("a pet with no remembered position lands in the work area's bottom-right corner", async () => {
  const pet = harness();

  await pet.controller.show();

  assert.deepEqual(pet.window().boundsWrites.at(-1), {
    x: workArea.width - desktopPetBody.width,
    y: workArea.height - desktopPetBody.height,
    width: desktopPetBody.width,
    height: desktopPetBody.height,
  });
});

test("a drag persists only the position the surface settled at", async () => {
  const pet = harness();
  await pet.controller.show();
  pet.resetSaveCount();

  // The renderer talks to the host directly; the controller never sees these.
  pet.surfaces.beginDrag(surfaceKey, { x: 72, y: 104 });
  pet.advance(100);
  assert.equal(pet.saveCount(), 0, "following the cursor must not write settings per frame");

  pet.surfaces.setPosition(surfaceKey, { x: 510, y: 460 });
  pet.surfaces.endDrag(surfaceKey);

  assert.equal(pet.saveCount(), 1);
  assert.deepEqual(pet.settings().positions["role-1:display-1"], { x: 510, y: 460 });
});

test("a release glide persists once, after the surface stops moving", async () => {
  const pet = harness();
  await pet.controller.show();
  pet.surfaces.setPosition(surfaceKey, { x: 900, y: 500 });
  pet.resetSaveCount();

  pet.surfaces.endDrag(surfaceKey, { x: -600, y: 0 });
  pet.advance(50);
  assert.equal(pet.saveCount(), 0, "a glide in flight must not write settings per frame");

  pet.advance(2_000);

  assert.equal(pet.saveCount(), 1);
  const persisted = pet.settings().positions["role-1:display-1"];
  assert.ok(persisted.x < 900, "the glide should have carried the pet leftward");
  assert.deepEqual(persisted, { x: pet.window().getBounds().x, y: 500 });
});

test("growing a bubble does not rewrite the persisted position", async () => {
  const pet = harness();
  await pet.controller.show();
  pet.resetSaveCount();

  // What the pet's surface renderer does once it has measured its own bubble.
  pet.surfaces.setExtension(surfaceKey, { side: "above", size: 126 });

  assert.equal(pet.saveCount(), 0);
  // The body stays put; only the window grows upward around it.
  assert.deepEqual(pet.window().boundsWrites.at(-1), {
    x: workArea.width - desktopPetBody.width,
    y: workArea.height - desktopPetBody.height - 126,
    width: desktopPetBody.width,
    height: desktopPetBody.height + 126,
  });
});

test("hiding the pet destroys its surface rather than leaving it invisible", async () => {
  const pet = harness();
  await pet.controller.show();

  await pet.controller.hide();

  assert.equal(pet.controller.isRunning, false);
  assert.equal(pet.window().isDestroyed(), true);
  assert.equal(pet.settings().visible, false);
});

test("disabling the plugin reclaims the pet's window", async () => {
  const pet = harness();
  await pet.controller.show();

  // What `ctx.effect("desktop_pet_controller", ...)` runs on teardown. This is
  // #181's acceptance criterion — "停用桌宠插件后 surface 全部回收" — at the
  // seam the plugin host actually calls.
  await pet.controller.terminate();

  assert.equal(pet.controller.isRunning, false);
  assert.equal(pet.window().isDestroyed(), true);
  assert.equal(pet.surfaces.has(surfaceKey), false);
});

test("a show still in flight when the plugin is disabled never reaches the screen", async () => {
  const pet = harness();

  // `resolveBinding` is a round trip to the Python backend, and the user can
  // disable the plugin inside it. Teardown then runs against a pet that does
  // not exist yet — and if the parked `show()` later resumes and creates its
  // surface, nothing is left to reclaim it: the effect scope is already
  // disposed, so #181's "停用后 surface 全部回收" would be false in exactly the
  // case nobody watches.
  pet.holdBinding();
  const showing = pet.controller.show();
  const terminating = pet.controller.terminate();
  pet.releaseBinding();
  await showing;
  await terminating;

  assert.equal(pet.windows.length, 0, "a disabled plugin must not open a window");
  assert.equal(pet.controller.isRunning, false);
  assert.equal(pet.surfaces.has(surfaceKey), false);
});

test("changing the package for one role reloads the active pet binding", async () => {
  const pet = harness({ visible: false, roleId: "role-1", packageId: "pet-1" });
  await pet.controller.show();
  pet.setPackageId("pet-2");

  await pet.controller.sync(true);

  const states = pet.window().payloads(surfaceStateChannel) as { load: { package: { id: string } } }[];
  assert.deepEqual(states.map((state) => state.load.package.id), ["pet-1", "pet-2"]);
  // Reusing the surface, not recreating it: the window survives a rebind.
  assert.equal(pet.windows.length, 1);
});

test("losing the binding hides the pet and clears the saved role", async () => {
  const pet = harness({ visible: true, roleId: "role-1", packageId: "pet-1" });
  await pet.controller.show();

  // What the user deleting the package, or switching the pet off in the role
  // form, looks like from here: `binding.get` answers with nothing.
  pet.setBinding(false);
  await pet.controller.sync();

  assert.equal(pet.controller.isRunning, false);
  assert.equal(pet.window().isDestroyed(), true);
  assert.deepEqual(
    { visible: pet.settings().visible, roleId: pet.settings().roleId, packageId: pet.settings().packageId },
    { visible: false, roleId: null, packageId: null },
  );
});

test("a play action is transient, so a reload does not replay a finished animation", async () => {
  const pet = harness(undefined, { greeting: "waving" });
  await pet.controller.show();

  pet.controller.handleAgentAction({
    action_id: "action-1",
    role_id: "role-1",
    session_key: "role:role-1",
    channel: "desktop",
    kind: "play",
    name: "greeting",
  });
  await pet.flush();

  assert.deepEqual(pet.window().payloads(surfaceMessageChannel), [{ state: "waving", transient: true }]);
  const retained = pet.window().payloads(surfaceStateChannel).at(-1) as { load: { state: string } };
  assert.equal(retained.load.state, "idle", "a transient action must not enter the retained state");
});

test("an agent move eases to the target corner and persists only the landing", async () => {
  const pet = harness(undefined, { greeting: "waving" });
  await pet.controller.show();
  pet.surfaces.setPosition(surfaceKey, { x: 0, y: 0 });
  pet.resetSaveCount();

  pet.controller.handleAgentAction({
    action_id: "action-1",
    role_id: "role-1",
    session_key: "role:role-1",
    channel: "desktop",
    kind: "move",
    target: "bottom_right",
    animation: "run",
  });
  await pet.flush();

  assert.deepEqual(pet.window().payloads(surfaceMessageChannel), [{ state: "running-right", transient: true }]);

  pet.advance(desktopPetAgentMoveDurationMs / 2);
  const midway = pet.window().getBounds();
  assert.ok(midway.x > 0 && midway.x < workArea.width - desktopPetBody.width, "the move should be animated, not instant");
  assert.equal(pet.saveCount(), 0, "a tween in flight must not write settings per frame");

  pet.advance(desktopPetAgentMoveDurationMs);

  assert.equal(pet.saveCount(), 1);
  assert.deepEqual(pet.settings().positions["role-1:display-1"], {
    x: workArea.width - desktopPetBody.width,
    y: workArea.height - desktopPetBody.height,
  });
});

test("an agent move to the centre accounts for the pet's own body size", async () => {
  const pet = harness();
  await pet.controller.show();

  pet.controller.handleAgentAction({
    action_id: "action-1",
    role_id: "role-1",
    session_key: "role:role-1",
    channel: "desktop",
    kind: "move",
    target: "center",
  });
  await pet.flush();
  pet.advance(desktopPetAgentMoveDurationMs * 2);

  assert.deepEqual(pet.settings().positions["role-1:display-1"], {
    x: (workArea.width - desktopPetBody.width) / 2,
    y: (workArea.height - desktopPetBody.height) / 2,
  });
});

test("agent actions for another role or a stopped pet are ignored", async () => {
  const pet = harness();
  const action = {
    action_id: "action-1",
    role_id: "role-2",
    session_key: "role:role-2",
    channel: "desktop" as const,
    kind: "move" as const,
    target: "top_left" as const,
  };

  // Not running yet.
  pet.controller.handleAgentAction({ ...action, role_id: "role-1" });
  await pet.flush();
  assert.equal(pet.windows.length, 0);

  await pet.controller.show();
  const writes = pet.window().boundsWrites.length;
  pet.controller.handleAgentAction(action);
  await pet.flush();
  pet.advance(desktopPetAgentMoveDurationMs * 2);

  assert.equal(pet.window().boundsWrites.length, writes, "another role must not move this pet");
});

test("a move whose surface disappeared while the work area was in flight is dropped", async () => {
  const pet = harness();
  await pet.controller.show();
  const window = pet.window();
  const writes = window.boundsWrites.length;

  pet.holdWorkArea();
  pet.controller.handleAgentAction({
    action_id: "action-1",
    role_id: "role-1",
    session_key: "role:role-1",
    channel: "desktop",
    kind: "move",
    target: "top_left",
  });
  // The work area answer is one IPC hop away; the pet can be switched off
  // inside that window, and moving a destroyed surface is a host error.
  await pet.controller.hide();
  pet.releaseWorkArea();
  await pet.flush();
  pet.advance(desktopPetAgentMoveDurationMs * 2);

  assert.equal(window.boundsWrites.length, writes);
  // And dropped *quietly*. Without the liveness re-check the move would still
  // not happen — the host refuses to move a surface it has forgotten — but it
  // would be refused by throwing, turning an ordinary race into a reported
  // failure every time a role moves the pet as the user switches it off.
  assert.deepEqual(pet.errors(), []);
});

test("the settled placement is reported to the renderer as well as to the plugin", async () => {
  const pet = harness();
  await pet.controller.show();

  const placements = pet.window().payloads(surfacePositionChannel) as {
    anchor: { x: number; y: number };
    bodyOffset: { x: number; y: number };
    workArea: typeof workArea;
  }[];
  assert.equal(placements.length, 1);
  assert.deepEqual(placements[0].workArea, workArea);
  assert.deepEqual(placements[0].bodyOffset, { x: 0, y: 0 });
});
