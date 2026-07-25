import assert from "node:assert/strict";
import test from "node:test";
import {
  VOICE_PRESS_THRESHOLD_MS,
  createVoiceInteractionState,
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
