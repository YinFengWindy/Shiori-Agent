import assert from "node:assert/strict";
import test from "node:test";
import {
  hasPetDragMoved,
  petGestureSelectsMainWindow,
  petDragRelease,
  petDragState,
  petHoverState,
  petDragVelocityMaximum,
} from "./interactionContract";

test("Codex pet interactions use jumping on hover and a four-pixel directional threshold", () => {
  assert.equal(petHoverState, "jumping");
  assert.equal(petDragState(120, 119), null);
  assert.equal(petDragState(120, 116), "running-left");
  assert.equal(petDragState(120, 124), "running-right");
});

test("Codex pet treats vertical movement as a drag without selecting a horizontal run row", () => {
  assert.equal(hasPetDragMoved(120, 160, 120, 163), false);
  assert.equal(hasPetDragMoved(120, 160, 120, 164), true);
  assert.equal(petDragState(120, 120), null);
});

test("Codex pet selects the main window only after a click gesture", () => {
  assert.equal(petGestureSelectsMainWindow(false), true);
  assert.equal(petGestureSelectsMainWindow(true), false);
});

test("Codex pet derives a bounded throw velocity from the recent meaningful drag samples", () => {
  const release = petDragRelease([
    { screenX: 100, screenY: 200, timeMs: 0 },
    { screenX: 104, screenY: 200, timeMs: 8 },
    { screenX: 180, screenY: 232, timeMs: 80 },
  ], { screenX: 260, screenY: 264, timeMs: 120 }, true);
  assert.equal(release.hasMoved, true);
  assert.deepEqual(release.sample, { screenX: 260, screenY: 264, timeMs: 120 });
  assert.deepEqual(release.velocity, { x: 1333.3333333333335, y: 533.3333333333334 });

  const capped = petDragRelease(
    [{ screenX: 0, screenY: 0, timeMs: 0 }],
    { screenX: 1000, screenY: 0, timeMs: 8 },
    true,
  );
  assert.equal(Math.hypot(capped.velocity?.x ?? 0, capped.velocity?.y ?? 0), petDragVelocityMaximum);
});

test("Codex pet does not throw after a click or a slow drag", () => {
  assert.deepEqual(
    petDragRelease([{ screenX: 100, screenY: 100, timeMs: 0 }], { screenX: 102, screenY: 100, timeMs: 16 }, false),
    { hasMoved: false, sample: { screenX: 102, screenY: 100, timeMs: 16 }, velocity: null },
  );
  assert.equal(
    petDragRelease([{ screenX: 100, screenY: 100, timeMs: 0 }], { screenX: 120, screenY: 100, timeMs: 160 }, true).velocity,
    null,
  );
});

test("Codex pet ignores tiny release jitter before estimating throw velocity", () => {
  const release = petDragRelease([
    { screenX: 0, screenY: 0, timeMs: 0 },
    { screenX: 80, screenY: 0, timeMs: 80 },
    { screenX: 81, screenY: 0, timeMs: 100 },
  ], { screenX: 82, screenY: 0, timeMs: 120 }, true);
  assert.deepEqual(release.velocity, { x: 1000, y: 0 });
});
