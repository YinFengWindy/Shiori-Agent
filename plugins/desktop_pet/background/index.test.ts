import { createPluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import assert from "node:assert/strict";
import test from "node:test";
import type {
  BackgroundCtx,
  PluginBackgroundSettled,
} from "../../../apps/desktop/renderer/src/background/pluginBackgroundRegistry";
import petBackground, {
  desktopPetTrayEntryId,
} from "./index";
import { desktopPetSurfaceId } from "./controller";

/**
 * Covers the wiring, not the behaviour behind it.
 *
 * `controller.test.ts` proves that a correctly-wired controller does the right
 * thing; this file proves the wiring exists and routes correctly, which is the
 * part #181-C actually wrote from scratch. The two failure modes it exists for
 * are both invisible to every other test and to the type checker: dropping one
 * of the four registrations (the `ctx.effect` one is what makes "停用即回收"
 * true at all), and mistranslating a command payload — `sync(undefined)` keeps
 * the pet's current visibility while `sync(false)` hides it, so one wrong
 * character turns the surface's "隐藏桌宠" menu entry into a no-op.
 */

/** The mutable bits a test both seeds and inspects. */
type RecorderState = {
  stored: unknown;
  /** Answers `binding.get`; throwing here rejects the call. */
  bindingAnswer: () => unknown;
};

type Recorder = {
  ctx: BackgroundCtx;
  effects: string[];
  events: Map<string, (payload: Record<string, unknown>) => void>;
  settled: Map<string, (settled: PluginBackgroundSettled) => void>;
  surfaceCalls: string[][];
  rpcCalls: string[];
  trayEntries: Map<string, { label: string; enabled: boolean }>;
  trayHandlers: Map<string, () => void>;
  state: RecorderState;
};

function recorder(overrides: Partial<RecorderState> = {}): Recorder {
  const effects: string[] = [];
  const events = new Map<string, (payload: Record<string, unknown>) => void>();
  const settled = new Map<string, (settled: PluginBackgroundSettled) => void>();
  const surfaceCalls: string[][] = [];
  const rpcCalls: string[] = [];
  const trayEntries = new Map<string, { label: string; enabled: boolean }>();
  const trayHandlers = new Map<string, () => void>();
  const state: RecorderState = {
    stored: overrides.stored ?? null,
    bindingAnswer: overrides.bindingAnswer ?? (() => ({
      binding: {
        role_id: "mira",
        package: { id: "pet-1", display_name: "Pet", spritesheet_abs: "C:/sheet.webp" },
        actions: {},
      },
    })),
  };
  return {
    effects,
    events,
    settled,
    surfaceCalls,
    rpcCalls,
    trayEntries,
    trayHandlers,
    state,
    ctx: {
      surfaces: {
        create: (surfaceId) => {
          surfaceCalls.push(["create", surfaceId]);
          return Promise.resolve({ x: 0, y: 0, displayId: "display-1" });
        },
        destroy: (surfaceId) => { surfaceCalls.push(["destroy", surfaceId]); return Promise.resolve(); },
        show: (surfaceId) => { surfaceCalls.push(["show", surfaceId]); },
        hide: (surfaceId) => { surfaceCalls.push(["hide", surfaceId]); },
        workArea: () => Promise.resolve({ x: 0, y: 0, width: 800, height: 600 }),
        setPosition: (surfaceId) => { surfaceCalls.push(["setPosition", surfaceId]); },
        moveTo: (surfaceId) => { surfaceCalls.push(["moveTo", surfaceId]); },
        post: (surfaceId) => { surfaceCalls.push(["post", surfaceId]); },
        setState: (surfaceId) => { surfaceCalls.push(["setState", surfaceId]); },
        onSettled: (surfaceId, handler) => { settled.set(surfaceId, handler); },
      },
      rpc: {
        ...createPluginRpcClient("desktop_pet"),
        handle: async (name, handler) => { events.set(name, handler); },
        call: <T,>(method: string) => {
          rpcCalls.push(method);
          return Promise.resolve(state.bindingAnswer() as T);
        },
      },
      events: { on: async (method, handler) => { events.set(method, (payload) => handler(payload, { id: "test", type: "event", method, payload })); return () => { events.delete(method); }; } },
      hostEvents: { on: (method, handler) => { events.set(method, (payload) => handler(payload, { id: "test", type: "event", method, payload })); } },
      store: {
        read: () => Promise.resolve(state.stored),
        write: (value) => { state.stored = value; return Promise.resolve(); },
      },
      assets: { url: (path) => (path ? `shiori-asset://local/${path}` : null) },
      tray: {
        setEntry: (entryId, entry) => {
          trayEntries.set(entryId, { label: entry.label, enabled: entry.enabled !== false });
          trayHandlers.set(entryId, entry.onClick);
        },
        removeEntry: (entryId) => { trayEntries.delete(entryId); trayHandlers.delete(entryId); },
      },
      effect: (label) => { effects.push(label); },
    },
  };
}

/** Lets the controller's internal promise chain drain. */
async function flush(): Promise<void> {
  for (let index = 0; index < 6; index += 1) await Promise.resolve();
}

test("setup registers every subscription the pet needs, and one reclaiming effect", async () => {
  const fake = recorder();

  await petBackground.setup(fake.ctx);

  // Without this effect the surface survives the plugin being disabled, and
  // #181's "停用桌宠插件后 surface 全部回收" quietly stops being true.
  assert.deepEqual(fake.effects, ["desktop_pet_controller"]);
  assert.deepEqual([...fake.events.keys()].sort(), [
        "action", "sync",
    "chat.done", "session.updated", "system.lock-state", "bubble.dismissed",
  ].sort());
  assert.deepEqual([...fake.settled.keys()], [desktopPetSurfaceId]);
});

test("setup restores a pet that was visible when the app last closed", async () => {
  const fake = recorder({ stored: { visible: true, roleId: "mira", packageId: "pet-1", positions: {} } });

  await petBackground.setup(fake.ctx);
  await flush();

  assert.deepEqual(fake.rpcCalls, ["binding.get"]);
  assert.ok(fake.surfaceCalls.some(([call]) => call === "create"), "the pet should be on screen");
});

test("setup leaves a pet that was hidden hidden, without creating a surface", async () => {
  const fake = recorder({ stored: { visible: false, roleId: "mira", packageId: "pet-1", positions: {} } });

  await petBackground.setup(fake.ctx);
  await flush();

  assert.deepEqual(fake.surfaceCalls.filter(([call]) => call === "create"), []);
});

test("a failed restore is reported, not rethrown, so the contribution stays alive", async () => {
  const fake = recorder({
    stored: { visible: true, roleId: "mira", packageId: "pet-1", positions: {} },
    bindingAnswer: () => { throw new Error("bridge 还没起来"); },
  });

  // A thrown `setup` makes `PluginBackgroundHost` dispose the whole scope, and
  // nothing retries it — the pet would stay dead until the app restarted.
  await assert.doesNotReject(petBackground.setup(fake.ctx));
  assert.deepEqual(fake.effects, ["desktop_pet_controller"]);
  assert.deepEqual([...fake.events.keys()].length, 6);
});

test("a sync command carries forceVisible through, and only when it is a boolean", async () => {
  const fake = recorder({ stored: { visible: true, roleId: "mira", packageId: "pet-1", positions: {} } });
  await petBackground.setup(fake.ctx);
  await flush();
  const command = fake.events.get("sync");
  assert.ok(command);

  // This is the surface's right-click "隐藏桌宠": `false` must reach
  // `sync(false)`, because `sync(undefined)` keeps the current visibility and
  // the menu entry would silently do nothing.
  command({ kind: "sync", forceVisible: false });
  await flush();
  assert.equal((fake.state.stored as { visible: boolean }).visible, false);

  // Absent, or present but not a boolean: neither may be read as "hide".
  command({ kind: "sync", forceVisible: "false" });
  await flush();
  assert.equal((fake.state.stored as { visible: boolean }).visible, false, "a string must not force anything");

  command({ kind: "sync" });
  await flush();
  assert.equal((fake.state.stored as { visible: boolean }).visible, false);
});

test("a role reply reaches the surface as retained state", async () => {
  const fake = recorder();
  await petBackground.setup(fake.ctx);
  await flush();
  fake.events.get("sync")?.({ kind: "show" });
  await flush();
  const before = fake.surfaceCalls.filter(([call]) => call === "setState").length;


  fake.events.get("chat.done")?.({ role_id: "mira", reply: "hi" });
  assert.equal(fake.surfaceCalls.filter(([call]) => call === "setState").length, before + 1);
});

test("a settle for the pet's surface reaches the controller", async () => {
  const fake = recorder();
  await petBackground.setup(fake.ctx);
  await flush();
  fake.events.get("sync")?.({ kind: "show" });
  await flush();

  fake.settled.get(desktopPetSurfaceId)?.({
    placement: {
      anchor: { x: 12, y: 34 },
      bodyOffset: { x: 0, y: 0 },
      workArea: { x: 0, y: 0, width: 800, height: 600 },
    },
    reason: "drag",
    displayId: "display-1",
  });
  await flush();

  assert.deepEqual(
    (fake.state.stored as { positions: Record<string, unknown> }).positions,
    { "mira:display-1": { x: 12, y: 34 } },
  );
});

test("the pet contributes its tray item as soon as it is enabled", async () => {
  const fake = recorder({ stored: { visible: false, roleId: "mira", packageId: "pet-1", positions: {} } });

  await petBackground.setup(fake.ctx);
  await flush();

  // The host used to build this item out of the pet's settings blob; since
  // #181-D the label and the enabled state are the plugin's to decide.
  assert.deepEqual(fake.trayEntries.get(desktopPetTrayEntryId), { label: "显示桌宠", enabled: true });
});

test("the tray item follows the pet, saying hide once it is showing", async () => {
  const fake = recorder({ stored: { visible: false, roleId: "mira", packageId: "pet-1", positions: {} } });
  await petBackground.setup(fake.ctx);
  await flush();

  fake.trayHandlers.get(desktopPetTrayEntryId)?.();
  await flush();
  assert.deepEqual(fake.trayEntries.get(desktopPetTrayEntryId), { label: "隐藏桌宠", enabled: true });

  fake.trayHandlers.get(desktopPetTrayEntryId)?.();
  await flush();
  assert.deepEqual(fake.trayEntries.get(desktopPetTrayEntryId), { label: "显示桌宠", enabled: true });
});

test("the tray item is disabled while no role has a pet package", async () => {
  const fake = recorder({
    stored: null,
    bindingAnswer: () => ({ binding: null }),
  });

  await petBackground.setup(fake.ctx);
  await flush();

  // What the host's `available` used to mean, now decided by the only code
  // that knows: a click here could not do anything.
  assert.deepEqual(fake.trayEntries.get(desktopPetTrayEntryId), { label: "显示桌宠", enabled: false });
});

test("clicking the tray item toggles the pet", async () => {
  const fake = recorder({ stored: { visible: false, roleId: "mira", packageId: "pet-1", positions: {} } });
  await petBackground.setup(fake.ctx);
  await flush();

  fake.trayHandlers.get(desktopPetTrayEntryId)?.();
  await flush();
  assert.ok(fake.surfaceCalls.some(([call]) => call === "create"), "show should put the pet on screen");
  assert.equal((fake.state.stored as { visible: boolean }).visible, true);

  fake.trayHandlers.get(desktopPetTrayEntryId)?.();
  await flush();
  assert.ok(fake.surfaceCalls.some(([call]) => call === "destroy"));
  assert.equal((fake.state.stored as { visible: boolean }).visible, false);
});
