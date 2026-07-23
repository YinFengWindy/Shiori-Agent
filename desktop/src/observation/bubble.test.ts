import assert from "node:assert/strict";
import test from "node:test";
import { ObservationBubbleController } from "./bubble.js";
import type { PetObservationPayload } from "./types.js";

test("transient bubbles expire while persistent bubbles wait for dismissal", async () => {
  const payloads: PetObservationPayload[] = [];
  const bubbles = new ObservationBubbleController((payload) => payloads.push(payload), 5);

  bubbles.publish("observing", true, "继续写吧", false);
  await new Promise((resolve) => setTimeout(resolve, 15));
  assert.equal(payloads.at(-1)?.bubble, "");

  bubbles.publish("failed", true, "观察失败", true);
  await new Promise((resolve) => setTimeout(resolve, 10));
  assert.equal(payloads.at(-1)?.bubble, "观察失败");
  bubbles.dismiss();
  assert.equal(payloads.at(-1)?.bubble, "");
});
