import assert from "node:assert/strict";
import test from "node:test";
import { DesktopObservationController } from "./controller.js";
import type { PetObservationPayload } from "./types.js";

test("enabling observation only grants the role tool and does not capture a screen", async () => {
  let enabled = false;
  const payloads: PetObservationPayload[] = [];
  const controller = new DesktopObservationController({
    pet: { isRunning: true, publishObservation: (payload) => payloads.push(payload) },
    getRoleId: () => "role-a",
    getEnabled: () => enabled,
    saveEnabled: async (next) => { enabled = next; },
  });

  await controller.start();

  assert.equal(enabled, true);
  assert.equal(controller.state, "observing");
  assert.equal(payloads.at(-1)?.bubble, "");
});

test("role-produced screen replies use the transient pet bubble", async () => {
  const payloads: PetObservationPayload[] = [];
  const controller = new DesktopObservationController({
    pet: { isRunning: true, publishObservation: (payload) => payloads.push(payload) },
    getRoleId: () => "role-a",
    getEnabled: () => true,
    saveEnabled: async () => undefined,
  });
  await controller.restore();

  controller.acceptRoleObservationReply("role-a", "我看到你在整理代码。\n继续吧。");
  controller.acceptRoleObservationReply("role-b", "这句不应显示。");

  assert.equal(payloads.at(-1)?.bubble, "我看到你在整理代码。\n继续吧。");
  assert.equal(payloads.at(-1)?.persistent, false);
});

test("hidden pets pause the tool capability without revoking persisted consent", async () => {
  const payloads: PetObservationPayload[] = [];
  const controller = new DesktopObservationController({
    pet: { isRunning: false, publishObservation: (payload) => payloads.push(payload) },
    getRoleId: () => "role-a",
    getEnabled: () => true,
    saveEnabled: async () => undefined,
  });

  await controller.restore();

  assert.equal(controller.state, "paused");
  assert.equal(payloads.at(-1)?.enabled, true);
});
