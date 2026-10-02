import assert from "node:assert/strict";
import test from "node:test";
import type { VoiceStatePayload } from "@shiori/sdk/contract";
import type { SurfaceTarget } from "../surface/host.js";
import type { VoiceInteractionState } from "./interactionState.js";
import type { DesktopVoiceController } from "./controller.js";
import { SurfaceVoiceController } from "./surfaceVoice.js";

function harness() {
  let targets: SurfaceTarget[] = [
    { key: { pluginId: "first", surfaceId: "view" }, windowId: 1, roleId: "a" },
    { key: { pluginId: "second", surfaceId: "view" }, windowId: 2, roleId: "b" },
  ];
  let state: VoiceInteractionState = { kind: "idle" };
  let accepts = true;
  const calls: unknown[][] = [];
  const states: { windowId: number; state: VoiceStatePayload }[] = [];
  const controller: Pick<DesktopVoiceController, "currentState" | "startPress" | "pointerMoved" | "release" | "cancel"> = {
    get currentState() { return state; },
    startPress: (source, roleId) => { calls.push(["press", source, roleId]); return accepts; },
    pointerMoved: (source) => { calls.push(["move", source]); },
    release: (source) => { calls.push(["release", source]); },
    cancel: (source) => { calls.push(["cancel", source]); state = { kind: "idle" }; },
  };
  const voice = new SurfaceVoiceController({
    interactionTargets: () => targets,
    publishVoice: (windowId, value) => { states.push({ windowId, state: value }); },
  }, controller);
  return { voice, calls, states, setTargets: (value: SurfaceTarget[]) => { targets = value; },
    setState: (value: VoiceInteractionState) => { state = value; }, reject: () => { accepts = false; } };
}

test("pointer gestures are bound to a live window and cannot release another surface's press", () => {
  const h = harness();
  h.voice.gesture(99, "press");
  assert.deepEqual(h.calls, []);
  h.voice.gesture(1, "press");
  h.voice.gesture(2, "release");
  h.voice.gesture(1, "move");
  h.voice.gesture(1, "release");
  h.voice.gesture(1, "cancel");
  assert.deepEqual(h.calls, [["press", "surface", "a"], ["move", "surface"], ["release", "surface"], ["cancel", "surface"]]);
});

test("busy ownership cannot be stolen and global hotkey retains the active target", () => {
  const h = harness();
  assert.equal(h.voice.startPress(2), true);
  h.setState({ kind: "waiting_reply" });
  assert.equal(h.voice.startPress(1), false);
  assert.equal(h.voice.startPress(), true);
  assert.deepEqual(h.calls, [["press", "surface", "b"], ["press", "hotkey", "b"]]);
  h.voice.publish({ status: "speaking" });
  assert.deepEqual(h.states, [{ windowId: 2, state: { status: "speaking" } }]);
});

test("role or lifecycle loss cancels the owner while an unchanged target preserves its press", () => {
  const h = harness();
  h.voice.startPress(1);
  h.voice.revalidate();
  assert.equal(h.calls.length, 1);
  h.setTargets([{ key: { pluginId: "first", surfaceId: "view" }, windowId: 1, roleId: "replacement" }]);
  h.voice.revalidate();
  assert.deepEqual(h.calls.at(-1), ["cancel", undefined]);
  assert.deepEqual(h.states.at(-1), { windowId: 1, state: { status: "idle" } });
  h.voice.startPress();
  assert.deepEqual(h.calls.at(-1), ["press", "hotkey", "replacement"]);
  h.setTargets([]);
  h.voice.revalidate();
  assert.equal(h.voice.startPress(), false);
});

test("accepted ownership transfer clears previous error while rejected input preserves its owner", () => {
  const h = harness();
  h.voice.startPress(1);
  h.setState({ kind: "error", message: "no microphone" });
  h.voice.publish({ status: "error", message: "no microphone" });
  h.reject();
  assert.equal(h.voice.startPress(2), false);
  h.voice.publish({ status: "error" });
  assert.equal(h.states.at(-1)?.windowId, 1);
  assert.equal(h.states.some((entry) => entry.state.status === "idle"), false);
  const accepted = harness();
  accepted.voice.startPress(1);
  accepted.setState({ kind: "error", message: "error" });
  assert.equal(accepted.voice.startPress(2), true);
  assert.deepEqual(accepted.states, [{ windowId: 1, state: { status: "idle" } }]);
});
