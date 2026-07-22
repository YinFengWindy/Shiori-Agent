import assert from "node:assert/strict";
import test from "node:test";
import { resolvePetActivityState, transitionPetActivity } from "./activity";

test("Codex pet activity keeps needs-input above blocked, ready, and running", () => {
  assert.equal(resolvePetActivityState({ active: "running", failed: "failed", ready: "review", waiting: "waiting" }), "waiting");
});

test("Codex pet maps desktop bridge task events to the documented animation rows", () => {
  const running = transitionPetActivity({}, {
    id: "request-1",
    type: "event",
    method: "chat.delta",
    payload: { session_key: "role-a" },
  });
  assert.equal(running.state, "running");

  const needsInput = transitionPetActivity(running.activities, {
    id: "proactive:role-b",
    type: "event",
    method: "session.updated",
    payload: {
      session: { key: "role-b", messages: [{ role: "assistant", metadata: { proactive: true } }] },
    },
  });
  assert.equal(needsInput.state, "waiting");
  assert.equal(needsInput.showNotification, true);

  const blocked = transitionPetActivity(needsInput.activities, {
    id: "request-1",
    type: "event",
    method: "chat.error",
    payload: { session_key: "role-a" },
  });
  assert.equal(blocked.state, "waiting");

  const reviewed = transitionPetActivity(blocked.activities, {
    id: "role-b",
    type: "event",
    method: "session.updated",
    payload: {
      session: { key: "role-b", messages: [{ role: "assistant", metadata: { proactive: false } }] },
    },
  });
  assert.equal(reviewed.state, "failed");
});
