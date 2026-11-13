import assert from "node:assert/strict";
import test from "node:test";
import type { BackgroundCtx, PluginBackgroundSettled } from "@yinfengwindy/shiori-sdk";
import type { PetProviderReport } from "@shiori-plugin/desktop_pet/provider";
import { deferred } from "@yinfengwindy/shiori-sdk/testing";
import { SpritePresentationController } from "./controller";

const identity = { request_id: "request", lease_id: "lease", role_id: "role", model_id: "model" };
const prepare = { ...identity, op: "prepare", spritesheet_abs: "C:/sprite.webp", body: { width: 192, height: 208 }, actions: { wave: "waving" } };
async function flush() { for (let i = 0; i < 20; i++) await Promise.resolve(); }
function harness() {
  const reports: PetProviderReport[] = [];
  const windows = new Map<string, { visible: boolean; state?: unknown }>();
  const messages = new Map<string, (value: unknown) => void>();
  const settlements = new Map<string, (value: PluginBackgroundSettled) => void>();
  let creation: Promise<void> = Promise.resolve();
  const surfaces: BackgroundCtx["surfaces"] = {
    onMessage: (id, handler) => { messages.set(id, handler); }, onSettled: (id, handler) => { settlements.set(id, handler); },
    create: async (id, spec) => { await creation; windows.set(id, { visible: spec.visible !== false }); return { x: 10, y: 20, displayId: "d" }; },
    destroy: async (id) => { windows.delete(id); }, show: (id) => { windows.get(id)!.visible = true; }, hide: (id) => { windows.get(id)!.visible = false; },
    setState: (id, state) => { windows.get(id)!.state = state; }, post: () => {}, setInteraction: () => {}, setPosition: () => {}, moveTo: () => {},
    workArea: async () => ({ x: 0, y: 0, width: 1000, height: 1000 }),
  };
  const controller = new SpritePresentationController({ surfaces, assets: { url: (path) => `shiori-asset://${path}` }, reportFailure: () => {} }, async (report) => { reports.push(report); });
  return { controller, reports, windows, messages, hold: (promise: Promise<void>) => { creation = promise; } };
}

test("prepare remains hidden and has no ready result until the real image reports loaded", async () => {
  const sprite = harness(); await sprite.controller.receive(prepare);
  assert.equal(sprite.windows.get("pet-lease")?.visible, false); assert.equal(sprite.reports.length, 0);
  sprite.messages.get("pet-lease")?.({ kind: "model.ready", lease_id: "lease" }); await flush();
  assert.equal(sprite.reports.at(-1)?.kind, "ready"); assert.equal(sprite.windows.get("pet-lease")?.visible, false);
  await sprite.controller.receive({ ...identity, request_id: "show", op: "show" });
  assert.equal(sprite.windows.get("pet-lease")?.visible, true); assert.equal(sprite.reports.at(-1)?.kind, "shown");
  await sprite.controller.dispose(); assert.equal(sprite.windows.size, 0);
});
test("close before native creation resolves prevents late loading from reviving the window", async () => {
  const sprite = harness(); const gate = deferred<void>(); sprite.hold(gate.promise);
  const preparing = sprite.controller.receive(prepare); await flush();
  const closing = sprite.controller.receive({ ...identity, request_id: "close", op: "close" });
  gate.resolve(); await Promise.all([preparing, closing]);
  sprite.messages.get("pet-lease")?.({ kind: "model.ready", lease_id: "lease" }); await flush();
  assert.equal(sprite.windows.size, 0); assert.equal(sprite.reports.some((report) => report.kind === "ready"), false);
  await sprite.controller.receive(prepare); assert.equal(sprite.windows.size, 0);
});
test("load failure destroys the prepared window and never emits readiness", async () => {
  const sprite = harness(); await sprite.controller.receive(prepare);
  sprite.messages.get("pet-lease")?.({ kind: "model.failed", lease_id: "lease" }); await flush();
  assert.equal(sprite.windows.size, 0); assert.deepEqual(sprite.reports.map((report) => report.kind), ["failed"]);
});
test("window lifecycle loss reports its exact lease and ignores unrelated windows", async () => {
  const sprite = harness(); await sprite.controller.receive(prepare);
  await sprite.controller.unavailable({ plugin_id: "other", surface_id: "pet-lease", status: "closed" }); assert.equal(sprite.windows.size, 1);
  await sprite.controller.unavailable({ plugin_id: "pet_codex_sprite", surface_id: "pet-lease", status: "unavailable" });
  assert.equal(sprite.windows.size, 0); assert.equal(sprite.reports.at(-1)?.kind, "lost");
  await sprite.controller.unavailable({ plugin_id: "pet_codex_sprite", surface_id: "pet-lease", status: "closed" });
  assert.equal(sprite.reports.length, 1);
});
