import assert from "node:assert/strict";
import test from "node:test";
import {
  advanceDesktopPetMomentum,
  desktopPetMomentumDecayPerFrame,
  shouldStopDesktopPetMomentum,
} from "./momentum.js";

test("desktop pet release momentum follows Codex's capped 32ms integration and velocity decay", () => {
  const next = advanceDesktopPetMomentum({ position: { x: 100, y: 200 }, velocity: { x: 1000, y: -500 } }, 48);
  assert.deepEqual(next.position, { x: 132, y: 184 });
  assert.deepEqual(next.velocity, {
    x: 1000 * desktopPetMomentumDecayPerFrame ** 2,
    y: -500 * desktopPetMomentumDecayPerFrame ** 2,
  });
});

test("desktop pet release momentum settles after Codex's duration or minimum-speed bound", () => {
  assert.equal(shouldStopDesktopPetMomentum({ position: { x: 0, y: 0 }, velocity: { x: 64, y: 0 } }, 20), true);
  assert.equal(shouldStopDesktopPetMomentum({ position: { x: 0, y: 0 }, velocity: { x: 80, y: 0 } }, 900), true);
  assert.equal(shouldStopDesktopPetMomentum({ position: { x: 0, y: 0 }, velocity: { x: 80, y: 0 } }, 899), false);
});
