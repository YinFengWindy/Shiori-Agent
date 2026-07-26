import assert from "node:assert/strict";
import test from "node:test";
import {
  VOICE_PRESS_THRESHOLD_MS,
  createVoiceInteractionState,
  isVoiceInteractionBusy,
  transitionVoiceInteraction,
} from "./interactionState.js";

test("a short press is cancelled and a long press starts recording", () => {
  const initial = createVoiceInteractionState();
  const pending = transitionVoiceInteraction(initial, {
    type: "press_started",
    source: "pet",
    atMs: 100,
  });

  assert.deepEqual(
    transitionVoiceInteraction(pending, { type: "released" }),
    { kind: "idle" },
  );

  const longPress = transitionVoiceInteraction(pending, {
    type: "press_elapsed",
    atMs: 100 + VOICE_PRESS_THRESHOLD_MS,
  });
  assert.deepEqual(longPress, { kind: "recording", source: "pet", startedAtMs: 100 });
});

test("movement wins over a pending pet voice press", () => {
  const pending = transitionVoiceInteraction(createVoiceInteractionState(), {
    type: "press_started",
    source: "pet",
    atMs: 0,
  });

  assert.deepEqual(
    transitionVoiceInteraction(pending, { type: "pointer_moved" }),
    { kind: "dragging" },
  );
});

test("releasing or cancelling a pet drag clears the interaction state", () => {
  let state = transitionVoiceInteraction(createVoiceInteractionState(), {
    type: "press_started",
    source: "pet",
    atMs: 0,
  });
  state = transitionVoiceInteraction(state, { type: "pointer_moved" });

  assert.deepEqual(
    transitionVoiceInteraction(state, { type: "released" }),
    { kind: "idle" },
  );
  assert.deepEqual(
    transitionVoiceInteraction(state, { type: "escape" }),
    { kind: "idle" },
  );
});

test("only active voice phases block a microphone test", () => {
  assert.equal(isVoiceInteractionBusy({ kind: "idle" }), false);
  assert.equal(isVoiceInteractionBusy({ kind: "dragging" }), false);
  assert.equal(isVoiceInteractionBusy({ kind: "error", message: "ASR 失败" }), false);
  assert.equal(isVoiceInteractionBusy({ kind: "press_pending", source: "pet", startedAtMs: 0 }), true);
  assert.equal(isVoiceInteractionBusy({ kind: "recording", source: "pet", startedAtMs: 0 }), true);
  assert.equal(isVoiceInteractionBusy({ kind: "waiting_reply" }), true);
  assert.equal(isVoiceInteractionBusy({ kind: "speaking", sentenceId: "s1" }), true);
});

test("recording release, empty ASR and chat failure are fail-closed", () => {
  let state = transitionVoiceInteraction(createVoiceInteractionState(), {
    type: "press_started",
    source: "hotkey",
    atMs: 0,
  });
  state = transitionVoiceInteraction(state, { type: "press_elapsed", atMs: 300 });
  state = transitionVoiceInteraction(state, { type: "released" });
  assert.equal(state.kind, "transcribing");

  state = transitionVoiceInteraction(state, { type: "asr_succeeded", text: "  " });
  assert.deepEqual(state, { kind: "error", message: "没有听清，请重试" });
  assert.deepEqual(
    transitionVoiceInteraction({ kind: "sending" }, {
      type: "chat_failed",
      message: "当前会话已有正在执行的聊天任务",
    }),
    { kind: "error", message: "当前会话已有正在执行的聊天任务" },
  );
});

test("recording startup failures and Esc leave no active voice task", () => {
  assert.deepEqual(
    transitionVoiceInteraction({ kind: "recording", source: "pet", startedAtMs: 0 }, {
      type: "recording_failed",
      message: "麦克风权限被拒绝",
    }),
    { kind: "error", message: "麦克风权限被拒绝" },
  );
  assert.deepEqual(
    transitionVoiceInteraction({ kind: "transcribing" }, { type: "escape" }),
    { kind: "idle" },
  );
  assert.deepEqual(
    transitionVoiceInteraction({ kind: "sending" }, { type: "escape" }),
    { kind: "idle" },
  );
});

test("a new input keeps the current sentence but drops later playback", () => {
  let state = transitionVoiceInteraction({ kind: "waiting_reply" }, {
    type: "reply_started",
    hasVoice: true,
  });
  state = transitionVoiceInteraction(state, { type: "sentence_ready", sentenceId: "s1" });
  state = transitionVoiceInteraction(state, { type: "new_input" });
  assert.deepEqual(state, { kind: "finish_current_sentence_then_idle", sentenceId: "s1" });

  assert.deepEqual(
    transitionVoiceInteraction(state, {
      type: "sentence_playback_finished",
      sentenceId: "s1",
      nextSentenceId: "s2",
    }),
    { kind: "idle" },
  );
});

test("stale playback events do not advance a different sentence", () => {
  const state = { kind: "speaking", sentenceId: "s2" } as const;
  assert.deepEqual(
    transitionVoiceInteraction(state, {
      type: "sentence_playback_finished",
      sentenceId: "s1",
    }),
    state,
  );
});
