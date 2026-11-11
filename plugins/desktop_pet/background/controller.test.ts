import assert from "node:assert/strict";
import test from "node:test";
import type { PetBinding, PetPresentationRequest, PetProviderReport } from "../provider";
import { DesktopPetController } from "./controller";
import { normalizeDesktopPetSettings } from "./settings";
import { deferred } from "@yinfengwindy/shiori-sdk/testing";

const provider = { plugin_id: "sprite", service_id: "models" };
const binding: PetBinding = { role_id: "r", provider, model: { id: "first", display_name: "One", body: { width: 200, height: 300 }, actions: ["wave"] } };
async function flush() { for (let i = 0; i < 30; i++) await Promise.resolve(); }

test("same-role model handover retains actual speech while role replacement clears it", async () => {
  const h = harness(); await h.controller.restore();
  const audio = { playback_id: "play", amplitude: .4 };
  h.controller.publishAudio(audio); await flush();
  await h.controller.select({ role_id: "r", provider, model_id: "second" });
  assert.deepEqual(h.commands.filter((command) => command.op === "show").at(-1)?.state?.audio, audio);
  h.binding({ ...binding, role_id: "other" }); await h.controller.sync();
  assert.equal(h.commands.filter((command) => command.op === "show").at(-1)?.state?.audio, null);
  await h.controller.terminate();
});
function harness(timeoutMs = 100) {
  const commands: PetPresentationRequest[] = [];
  const visible = new Set<string>();
  const committed: string[] = [];
  const targets: string[] = [];
  const errors: unknown[] = [];
  let answer: PetBinding | null = binding;
  let hold = false;
  let rejectPrepare = false;
  let rejectCommit = false;
  let unavailable = false;
  let largestVisible = 0;
  let delayedKind: "hidden" | "shown" | null = null;
  let delayedReport: { command: PetPresentationRequest; kind: "hidden" | "shown" } | null = null;
  let commitGate: Promise<void> = Promise.resolve();
  let committing = false;
  const controller = new DesktopPetController({
    settings: normalizeDesktopPetSettings(null), timeoutMs,
    saveSettings: async () => {}, resolveBinding: async () => answer,
    preview: async (roleId, ref) => ({ ...binding, role_id: roleId, provider: ref.provider, model: { ...binding.model, id: ref.model_id } }),
    select: async (_roleId, ref) => { committing = true; await commitGate; if (rejectCommit) throw new Error("save failed"); committed.push(ref.model_id); },
    onError: (_op, error) => errors.push(error),
    services: {
      list: async () => ({ services: [] }),
      call: async <T,>(_service: unknown, _method: string, payload?: Record<string, unknown>) => {
        const command = payload as PetPresentationRequest;
        commands.push(command);
        if (unavailable) throw new Error("provider unavailable");
        if (command.op === "prepare" && rejectPrepare) { report(command, "failed"); }
        else if (command.op === "prepare" && !hold) report(command, "ready");
        else if (command.op === "show") { visible.add(command.lease_id); largestVisible = Math.max(largestVisible, visible.size); complete(command, "shown"); }
        else if (command.op === "hide") { visible.delete(command.lease_id); complete(command, "hidden"); }
        else if (command.op === "close") { visible.delete(command.lease_id); report(command, "closed"); }
        return { accepted: true } as T;
      },
    },
  });
  const report = (command: PetPresentationRequest, kind: PetProviderReport["kind"]) => controller.report({ ...command, kind, error: kind === "failed" ? "load failed" : undefined });
  const complete = (command: PetPresentationRequest, kind: "hidden" | "shown") => {
    if (kind === delayedKind) { delayedKind = null; delayedReport = { command, kind }; }
    else report(command, kind);
  };
  controller.watchTarget((role) => targets.push(role));
  return { controller, commands, visible, committed, targets, errors, report, maxVisible: () => largestVisible,
    delay: (kind: "hidden" | "shown") => { delayedKind = kind; }, delayed: () => delayedReport,
    release: () => { if (delayedReport) { report(delayedReport.command, delayedReport.kind); delayedReport = null; } },
    holdCommit: (promise: Promise<void>) => { commitGate = promise; }, committing: () => committing,
    hold: (value: boolean) => { hold = value; }, fail: () => { rejectPrepare = true; }, failCommit: () => { rejectCommit = true; },
    available: (value: boolean) => { unavailable = !value; }, binding: (value: PetBinding | null) => { answer = value; } };
}
const selection = (model_id: string) => ({ role_id: "r", provider, model_id });

test("same-role handover keeps output binding and never displays two models", async () => {
  const pet = harness(); await pet.controller.show();
  pet.controller.replies.show({ source: "live" }, "r", "直播回复", { kind: "hold" });
  pet.hold(true);
  const switching = pet.controller.select(selection("second")); await flush();
  assert.equal(pet.visible.size, 1); assert.deepEqual(pet.committed, []);
  const prepare = pet.commands.filter((command) => command.op === "prepare").at(-1)!;
  pet.report(prepare, "ready"); await switching;
  assert.deepEqual(pet.committed, ["second"]); assert.deepEqual(pet.targets, ["r"]);
  assert.equal(pet.maxVisible(), 1);
  assert.equal(pet.commands.filter((command) => command.op === "update").at(-1)?.state?.reply.text, "直播回复");
  await pet.controller.terminate();
});
test("a failed candidate keeps the old selection and active window", async () => {
  const pet = harness(); await pet.controller.show(); const previous = [...pet.visible]; pet.fail();
  await assert.rejects(pet.controller.select(selection("broken")), /load failed/);
  assert.deepEqual([...pet.visible], previous); assert.deepEqual(pet.committed, []); assert.deepEqual(pet.targets, ["r"]);
  await pet.controller.terminate();
});
test("a failed selection write restores the old window without overlap", async () => {
  const pet = harness(); await pet.controller.show(); const previous = [...pet.visible]; pet.failCommit();
  await assert.rejects(pet.controller.select(selection("second")), /save failed/);
  assert.deepEqual([...pet.visible], previous); assert.equal(pet.maxVisible(), 1); assert.deepEqual(pet.committed, []);
  await pet.controller.terminate();
});
test("hide revokes a pending prepare and a late ready cannot reopen it", async () => {
  const pet = harness(); pet.hold(true);
  const showing = pet.controller.show(); const rejected = assert.rejects(showing, /撤销/); await flush();
  const prepare = pet.commands.find((command) => command.op === "prepare")!;
  await pet.controller.hide(); await rejected; pet.report(prepare, "ready"); await flush();
  assert.equal(pet.visible.size, 0); assert.equal(pet.controller.currentSettings.visible, false); assert.deepEqual(pet.targets, []);
  await pet.controller.terminate();
});
test("timeout closes the candidate and ignores stale readiness", async () => {
  const pet = harness(5); pet.hold(true);
  await assert.rejects(pet.controller.show(), /超时/);
  const prepare = pet.commands.find((command) => command.op === "prepare")!; pet.report(prepare, "ready"); await flush();
  assert.equal(pet.visible.size, 0); assert.equal(pet.commands.at(-1)?.op, "close"); await pet.controller.terminate();
});
test("provider availability retries startup but cannot undo a later hide", async () => {
  const pet = harness(); pet.available(false); await assert.rejects(pet.controller.restore(), /unavailable/);
  pet.available(true); await pet.controller.available("sprite"); assert.equal(pet.visible.size, 1);
  await pet.controller.hide(); await pet.controller.available("sprite"); assert.equal(pet.visible.size, 0);
  await pet.controller.terminate();
});
test("provider loss retires only the matching role and lease", async () => {
  const pet = harness(); await pet.controller.show(); const prepare = pet.commands[0];
  pet.controller.report({ ...prepare, lease_id: "old", kind: "lost" }); assert.equal(pet.controller.isRunning, true);
  pet.report(prepare, "lost"); await flush(); assert.equal(pet.controller.isRunning, false); assert.deepEqual(pet.targets, ["r", ""]);
  assert.equal(pet.controller.currentSettings.model?.model_id, "first"); await pet.controller.terminate();
});

test("a newer selection of the old model restores visibility after an interrupted handover", async (context) => {
  for (const boundary of ["hidden", "shown", "commit"] as const) await context.test(boundary, async () => {
    const pet = harness(); await pet.controller.show(); const original = [...pet.visible];
    const gate = deferred<void>();
    if (boundary === "commit") pet.holdCommit(gate.promise); else pet.delay(boundary);
    const switching = pet.controller.select(selection("second"));
    // A newer UI context can accept another request while the first context has
    // disconnected; provider effects and backend writes already accepted continue.
    const interrupted = switching.catch(() => {});
    await flush();
    if (boundary === "commit") assert.equal(pet.committing(), true);
    else assert.ok(pet.delayed());
    const selectingOriginal = pet.controller.select(selection("first"));
    if (boundary === "commit") gate.resolve(); else pet.release();
    await Promise.all([interrupted, selectingOriginal]);
    assert.deepEqual([...pet.visible], original, "the original lease must be visible after reselecting it");
    assert.equal(pet.controller.isRunning, true);
    assert.equal(pet.controller.currentSettings.visible, true);
    assert.equal(pet.controller.currentSettings.model?.model_id, "first");
    assert.equal(pet.committed.at(-1), "first");
    assert.equal(pet.maxVisible(), 1);
    assert.deepEqual(pet.targets, ["r"], "model handover must not restart shared speech/live ownership");
    await pet.controller.terminate();
  });
});

test("an explicit hide during handover cannot be undone by old-window recovery", async () => {
  const pet = harness(); await pet.controller.show(); pet.delay("hidden");
  const switching = pet.controller.select(selection("second"));
  const interrupted = switching.catch(() => {});
  await flush(); assert.ok(pet.delayed());
  const hiding = pet.controller.hide(); pet.release();
  await Promise.all([interrupted, hiding]);
  assert.equal(pet.visible.size, 0);
  assert.equal(pet.controller.isRunning, false);
  assert.equal(pet.controller.currentSettings.visible, false);
  assert.equal(pet.commands.filter((command) => command.op === "show").length, 1);
  assert.deepEqual(pet.committed, []);
  await pet.controller.terminate();
});

test("host provider retirement clears an orphaned active lease and reenable creates a new window", async () => {
  const pet = harness(); await pet.controller.show(); const previous = pet.commands[0];
  const selected = pet.controller.currentSettings.model;
  pet.controller.publishAudio({ playback_id: "old-play", amplitude: 0.8 });
  const beforeRetirement = pet.commands.length;
  pet.visible.clear(); // Native cleanup closes the window after its provider RPC owner is gone.
  pet.controller.providersReloaded({ generation: 1, plugin_ids: ["sprite"], disabled_plugin_ids: ["sprite"] });
  assert.equal(pet.controller.isRunning, false); assert.equal(pet.controller.visibleRoleId, "");
  assert.deepEqual(pet.controller.currentSettings.model, selected); assert.equal(pet.controller.currentSettings.visible, true);
  assert.equal(pet.commands.length, beforeRetirement, "retiring output must not publish through a successor provider with the old lease");
  pet.report(previous, "shown"); pet.report(previous, "ready");
  assert.equal(pet.controller.isRunning, false);
  pet.controller.providersReloaded({ generation: 1, plugin_ids: ["sprite"], disabled_plugin_ids: [] });
  await pet.controller.available("sprite");
  assert.equal(pet.visible.size, 1); assert.equal(pet.controller.isRunning, true);
  const next = pet.commands.filter((command) => command.op === "prepare").at(-1)!;
  assert.notEqual(next.lease_id, previous.lease_id);
  assert.equal(next.state?.audio, null); assert.deepEqual(pet.targets, ["r", "", "r"]);
  await pet.controller.terminate();
});

test("provider retirement cancels a pending prepare, while unrelated and no-op reloads preserve it", async () => {
  const pet = harness(); pet.hold(true);
  const showing = pet.controller.show(); const rejected = assert.rejects(showing, /撤销/); await flush();
  const previous = pet.commands[0];
  pet.controller.providersReloaded({ plugin_ids: [], disabled_plugin_ids: [] });
  pet.controller.providersReloaded({ plugin_ids: ["other"], disabled_plugin_ids: ["other"] });
  assert.equal(pet.commands.length, 1);
  pet.controller.providersReloaded({ plugin_ids: ["sprite"], disabled_plugin_ids: ["sprite"] });
  await rejected;
  pet.report(previous, "ready"); await flush();
  assert.equal(pet.visible.size, 0);
  assert.equal(pet.commands.length, 1, "retired leases must not send cleanup to a successor provider");
  pet.hold(false); pet.controller.providersReloaded({ plugin_ids: ["sprite"], disabled_plugin_ids: [] });
  await pet.controller.available("sprite"); assert.equal(pet.visible.size, 1);
  await pet.controller.terminate();
});

test("hide and newer selection supersede provider recovery without touching unrelated active models", async () => {
  const pet = harness(); await pet.controller.show(); const original = [...pet.visible];
  pet.controller.providersReloaded({ plugin_ids: ["other"], disabled_plugin_ids: [] });
  pet.controller.providersReloaded({ plugin_ids: [], disabled_plugin_ids: [] });
  assert.deepEqual([...pet.visible], original); assert.deepEqual(pet.targets, ["r"]);
  pet.visible.clear(); pet.controller.providersReloaded({ plugin_ids: ["sprite"], disabled_plugin_ids: ["sprite"] });
  const hiding = pet.controller.hide();
  pet.controller.providersReloaded({ plugin_ids: ["sprite"], disabled_plugin_ids: [] });
  await pet.controller.available("sprite"); await hiding; assert.equal(pet.visible.size, 0);
  await pet.controller.show(); pet.visible.clear();
  pet.controller.providersReloaded({ plugin_ids: ["sprite"], disabled_plugin_ids: ["sprite"] });
  await pet.controller.select({ role_id: "r", provider: { plugin_id: "new", service_id: "models" }, model_id: "new-model" });
  pet.controller.providersReloaded({ plugin_ids: ["sprite"], disabled_plugin_ids: [] });
  await pet.controller.available("sprite");
  assert.equal(pet.visible.size, 0); assert.equal(pet.controller.currentSettings.model?.provider.plugin_id, "new");
  await pet.controller.terminate();
});
