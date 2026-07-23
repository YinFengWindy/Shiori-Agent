import assert from "node:assert/strict";
import test from "node:test";
import { DesktopObservationController } from "./controller.js";
import type { PetObservationPayload } from "./types.js";

test("visible pets activate only the role-reply bubble surface", async () => {
  const payloads: PetObservationPayload[] = [];
  const controller = new DesktopObservationController({
    pet: { isRunning: true, publishObservation: (payload) => payloads.push(payload) },
    getRoleId: () => "role-a",
  });

  await controller.restore();

  assert.equal(controller.state, "observing");
  assert.equal(payloads.at(-1)?.bubble, "");
});

test("role-produced screen replies use the transient pet bubble", async () => {
  const payloads: PetObservationPayload[] = [];
  const controller = new DesktopObservationController({
    pet: { isRunning: true, publishObservation: (payload) => payloads.push(payload) },
    getRoleId: () => "role-a",
  });
  await controller.restore();

  controller.acceptRoleObservationReply("role-a", "我看到你在整理代码。\n继续吧。");
  controller.acceptRoleObservationReply("role-b", "这句不应显示。");

  assert.equal(payloads.at(-1)?.bubble, "我看到你在整理代码。\n继续吧。");
  assert.equal(payloads.at(-1)?.persistent, false);
});

test("hidden pets clear bubbles without changing the role tool capability", async () => {
  const payloads: PetObservationPayload[] = [];
  let isRunning = true;
  const controller = new DesktopObservationController({
    pet: {
      get isRunning() { return isRunning; },
      publishObservation: (payload) => payloads.push(payload),
    },
    getRoleId: () => "role-a",
  });

  await controller.restore();
  controller.acceptRoleObservationReply("role-a", "这句会在隐藏时清除。");
  isRunning = false;
  await controller.restore();

  assert.equal(controller.state, "off");
  assert.equal(payloads.at(-1)?.bubble, "");
  assert.equal(payloads.at(-1)?.enabled, true);
});
