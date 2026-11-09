import assert from "node:assert/strict";
import test from "node:test";
import type { PetBinding, PetPresentationRequest, PetProviderReport } from "@yinfengwindy/shiori-pet";
import { DesktopPetController } from "./controller";
import { normalizeDesktopPetSettings } from "./settings";

const provider = { plugin_id: "sprite", service_id: "models" };
const binding: PetBinding = { role_id: "r", provider, model: { id: "first", display_name: "One", body: { width: 200, height: 300 }, actions: ["wave"] } };
async function flush() { for (let i = 0; i < 30; i++) await Promise.resolve(); }
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
  const controller = new DesktopPetController({
    settings: normalizeDesktopPetSettings(null), timeoutMs,
    saveSettings: async () => {}, resolveBinding: async () => answer,
    preview: async (roleId, ref) => ({ ...binding, role_id: roleId, provider: ref.provider, model: { ...binding.model, id: ref.model_id } }),
    select: async (_roleId, ref) => { if (rejectCommit) throw new Error("save failed"); committed.push(ref.model_id); },
    onError: (_op, error) => errors.push(error),
    services: {
      list: async () => ({ services: [] }),
      call: async <T,>(_service: unknown, _method: string, payload?: Record<string, unknown>) => {
        const command = payload as PetPresentationRequest;
        commands.push(command);
        if (unavailable) throw new Error("provider unavailable");
        if (command.op === "prepare" && rejectPrepare) { report(command, "failed"); }
        else if (command.op === "prepare" && !hold) report(command, "ready");
        else if (command.op === "show") { visible.add(command.lease_id); largestVisible = Math.max(largestVisible, visible.size); report(command, "shown"); }
        else if (command.op === "hide") { visible.delete(command.lease_id); report(command, "hidden"); }
        else if (command.op === "close") { visible.delete(command.lease_id); report(command, "closed"); }
        return { accepted: true } as T;
      },
    },
  });
  const report = (command: PetPresentationRequest, kind: PetProviderReport["kind"]) => controller.report({ ...command, kind, error: kind === "failed" ? "load failed" : undefined });
  controller.watchTarget((role) => targets.push(role));
  return { controller, commands, visible, committed, targets, errors, report, maxVisible: () => largestVisible,
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
