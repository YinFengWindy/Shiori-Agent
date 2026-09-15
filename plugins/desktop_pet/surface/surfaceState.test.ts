import assert from "node:assert/strict";
import test from "node:test";
import {
  petSurfaceLoadSignature,
  readPetSurfaceMessage,
  readPetSurfaceState,
} from "./surfaceState";

const load = { package: { spritesheetUrl: "mira-asset://pet" }, state: "idle" };

test("a retained payload carries the package, the sprite state and the reply", () => {
  assert.deepEqual(
    readPetSurfaceState({
      load,
      reply: { paused: false, text: "继续写吧", persistent: false },
    }),
    {
      load: { package: { spritesheetUrl: "mira-asset://pet" }, state: "idle" },
      reply: { paused: false, text: "继续写吧", persistent: false },
    },
  );
});

test("a payload without a reply is still usable", () => {
  const parsed = readPetSurfaceState({ load });
  assert.equal(parsed?.reply, null);
  assert.equal(parsed?.load.state, "idle");
});

test("a payload with no recognizable sprite state is rejected outright", () => {
  assert.equal(readPetSurfaceState({ load: { ...load, state: "dancing" } }), null);
  assert.equal(readPetSurfaceState({ load: { package: {}, state: "idle" } }), null);
  assert.equal(readPetSurfaceState({ load: null }), null);
  assert.equal(readPetSurfaceState(null), null);
  assert.equal(readPetSurfaceState("idle"), null);
});

test("a malformed reply degrades to none rather than rejecting the package", () => {
  const parsed = readPetSurfaceState({ load, reply: { status: "nonsense", enabled: true } });
  assert.equal(parsed?.reply, null);
  assert.equal(parsed?.load.package.spritesheetUrl, "mira-asset://pet");
});

test("a bubble that is not a string is rejected", () => {
  const parsed = readPetSurfaceState({ load, reply: { paused: false, text: { toString: 1 } } });
  assert.equal(parsed?.reply, null);
});

test("a transient play request is distinguished from a base state change", () => {
  assert.deepEqual(readPetSurfaceMessage({ state: "waving", transient: true }), {
    state: "waving",
    transient: true,
  });
  assert.deepEqual(readPetSurfaceMessage({ state: "waving" }), {
    state: "waving",
    transient: false,
  });
  assert.equal(readPetSurfaceMessage({ state: "dancing" }), null);
  assert.equal(readPetSurfaceMessage(undefined), null);
});

test("the load signature changes with the package and with the sprite state", () => {
  assert.equal(
    petSurfaceLoadSignature({ package: { spritesheetUrl: "a" }, state: "idle" }),
    petSurfaceLoadSignature({ package: { spritesheetUrl: "a" }, state: "idle" }),
  );
  assert.notEqual(
    petSurfaceLoadSignature({ package: { spritesheetUrl: "a" }, state: "idle" }),
    petSurfaceLoadSignature({ package: { spritesheetUrl: "b" }, state: "idle" }),
  );
  assert.notEqual(
    petSurfaceLoadSignature({ package: { spritesheetUrl: "a" }, state: "idle" }),
    petSurfaceLoadSignature({ package: { spritesheetUrl: "a" }, state: "waiting" }),
  );
});
