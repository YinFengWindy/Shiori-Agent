import assert from "node:assert/strict";
import test from "node:test";
import type { BackgroundCtx, PluginBackgroundSettled } from "@yinfengwindy/shiori-sdk";
import { createFakePluginClient } from "@yinfengwindy/shiori-sdk/testing";
import { defaultVoicePreferences } from "./voice/preferences";
import petBackground from "./index";
import type { PetPresentationRequest } from "@yinfengwindy/shiori-pet";

/**
 * Covers the wiring, not the behaviour behind it.
 *
 * `./controller.test.ts` proves
 * that a correctly-wired controller does the right thing; this file proves the wiring exists and routes correctly, which is the
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
  providerCalls: PetPresentationRequest[];
  trayEntries: Map<string, { label: string; enabled: boolean }>;
  trayHandlers: Map<string, () => void>;
  /** What reached `ctx.reportFailure`, the host's diagnostic log. */
  failures: [string, unknown][];
  state: RecorderState;
};

function recorder(overrides: Partial<RecorderState> = {}): Recorder {
  const effects: string[] = [];
  const events = new Map<string, (payload: Record<string, unknown>) => void>();
  const settled = new Map<string, (settled: PluginBackgroundSettled) => void>();
  const surfaceCalls: string[][] = [];
  const rpcCalls: string[] = [];
  const providerCalls: PetPresentationRequest[] = [];
  const trayEntries = new Map<string, { label: string; enabled: boolean }>();
  const trayHandlers = new Map<string, () => void>();
  const failures: [string, unknown][] = [];
  const state: RecorderState = {
    stored: overrides.stored ?? null,
    bindingAnswer: overrides.bindingAnswer ?? (() => ({
      binding: {
        role_id: "mira",
        provider: { plugin_id: "pet_codex_sprite", service_id: "models" },
        model: { id: "pet-1", display_name: "Pet", body: { width: 192, height: 208 }, actions: [] },
      },
    })),
  };
  return {
    effects,
    events,
    settled,
    surfaceCalls,
    rpcCalls,
    providerCalls,
    trayEntries,
    trayHandlers,
    failures,
    state,
    ctx: {
      native: { audio: { devices: async () => [], startCapture: async () => {}, stopCapture: async () => ({ audio_base64: "", format: "wav" }), cancelCapture: async () => {}, play: async () => {}, stop: async () => {} }, keys: { validate: async () => {}, register: async () => {}, unregister: async () => {} } },
      chat: { send: async () => ({}), cancel: async () => ({}) },
      surfaces: {
        onMessage: () => {},
        setInteraction: () => {},
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
      rpc: createFakePluginClient({
        handle: async (name, handler) => { events.set(name, handler); },
        services: { list: async () => ({services: []}), call: async <T,>(_provider: unknown, _method: string, payload?: Record<string, unknown>) => {
          const command = payload as PetPresentationRequest;
          providerCalls.push(command);
          const kind = command.op === "prepare" ? "ready" : command.op === "show" ? "shown" : command.op === "hide" ? "hidden" : command.op === "close" ? "closed" : null;
          if (kind) events.get("provider.report")?.({ ...command, kind });
          return {accepted: true} as T;
        } },
        call: <T,>(method: string) => {
          rpcCalls.push(method);
          return Promise.resolve((method === "voice.preferences.get" ? defaultVoicePreferences : state.bindingAnswer()) as T);
        },
      }),
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
      reportFailure: (operation, error) => { failures.push([operation, error]); },
    },
  };
}

/** Lets the controller's internal promise chain drain. */
async function flush(): Promise<void> {
  for (let index = 0; index < 40; index += 1) await Promise.resolve();
}

test("restores through provider while desktop owns no surface", async () => {
  const fake = recorder({ stored: { visible: true, roleId: "mira", packageId: "pet-1", positions: {} } });
  await petBackground.setup(fake.ctx); await flush();
  assert.equal(fake.providerCalls.some((command) => command.op === "show"), true);
  assert.deepEqual(fake.surfaceCalls, []);
});
test("saved hidden state is not undone by a provider becoming available", async () => {
  const fake = recorder({ stored: { visible: false, roleId: "mira", packageId: "pet-1", positions: {} } });
  await petBackground.setup(fake.ctx); await flush();
  fake.events.get("provider.available")?.({plugin_id: "pet_codex_sprite"}); await flush();
  assert.deepEqual(fake.providerCalls, []);
});
test("chat and live replies both reach the selected provider and live outcome returns", async () => {
  const fake = recorder(); await petBackground.setup(fake.ctx); await flush();
  fake.events.get("chat.done")?.({role_id: "mira", reply: "普通回复"}); await flush();
  assert.equal(fake.providerCalls.at(-1)?.state?.reply.text, "普通回复");
  fake.events.get("live.reply.show")?.({source: "live", role_id: "mira", reply_id: "r1", run_id: "run", text: "直播回复"}); await flush();
  assert.equal(fake.providerCalls.at(-1)?.state?.reply.text, "直播回复");
  assert.equal(fake.rpcCalls.includes("live.reply.outcome"), true);
  fake.events.get("sync")?.({forceVisible: false}); await flush();
  assert.equal(fake.providerCalls.at(-1)?.op, "close");
});
test("provider report identities isolate foreign gestures from the visible role", async () => {
  const fake = recorder(); await petBackground.setup(fake.ctx); await flush();
  const prepare = fake.providerCalls[0];
  fake.events.get("provider.report")?.({...prepare, role_id: "other", kind: "gesture", gesture: {kind: "hide"}}); await flush();
  assert.equal(fake.providerCalls.some((command) => command.op === "close"), false);
  fake.events.get("provider.report")?.({...prepare, kind: "gesture", gesture: {kind: "hide"}}); await flush();
  assert.equal(fake.providerCalls.at(-1)?.op, "close");
});
