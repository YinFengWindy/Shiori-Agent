import assert from "node:assert/strict";
import test from "node:test";
import { createVoicePlaybackCallbacks, handleVoiceBridgeEvent, selectVoiceTurn } from "./bridgeEvents.js";
import type { VoicePlaybackItem } from "./playback.js";

test("selects the new playback turn and cancels only the previous backend turn", async () => {
  const calls: Array<[string, string]> = [];
  const playback = {
    beginTurn: (turnId: string) => calls.push(["begin", turnId]),
  };
  const bridge = {
    invoke: async (request: { method: string; payload: Record<string, unknown> }) => {
      calls.push([request.method, String(request.payload.voice_turn_id || "")]);
      return {
        id: "cancel-1",
        type: "response" as const,
        method: request.method,
        payload: {},
        error: null,
      };
    },
  };

  await selectVoiceTurn(bridge, playback, "old-turn", "new-turn");

  assert.deepEqual(calls, [
    ["begin", "new-turn"],
    ["voice.turn.cancel", "old-turn"],
  ]);
});

test("ignores stale voice events and enqueues audio only for the current turn", () => {
  const actions: string[] = [];
  const controller = {
    currentTurnId: "new-turn",
    replyStarted: () => actions.push("reply-started"),
    sentenceReady: (id: string) => actions.push(`sentence:${id}`),
    ttsFailed: () => actions.push("tts-failed"),
  };
  const enqueued: VoicePlaybackItem[] = [];
  const playback = {
    enqueue: (item: VoicePlaybackItem) => enqueued.push(item),
    finishTurn: (turnId: string) => actions.push(`finished:${turnId}`),
  };
  const event = (method: string, turnId: string) => ({
    id: "request-1",
    type: "event" as const,
    method,
    payload: {
      voice_turn_id: turnId,
      request_id: "request-1",
      sequence: 0,
      audio_base64: "AA==",
      session_key: "role:mira",
      text: "你好。",
      message: "failed",
      has_voice: true,
    },
  });

  handleVoiceBridgeEvent(event("voice.reply.started", "old-turn"), controller, playback);
  handleVoiceBridgeEvent(event("voice.tts.audio", "old-turn"), controller, playback);
  handleVoiceBridgeEvent(event("voice.tts.error", "old-turn"), controller, playback);
  handleVoiceBridgeEvent(event("voice.reply.started", "new-turn"), controller, playback);
  handleVoiceBridgeEvent(event("voice.tts.audio", "new-turn"), controller, playback);
  handleVoiceBridgeEvent(event("voice.tts.finished", "old-turn"), controller, playback);
  handleVoiceBridgeEvent(event("voice.tts.finished", "new-turn"), controller, playback);

  assert.deepEqual(actions, ["reply-started", "sentence:request-1:0", "finished:new-turn"]);
  assert.deepEqual(enqueued, [{
    id: "request-1:0",
    turnId: "new-turn",
    sessionKey: "role:mira",
    requestId: "request-1",
    sequence: 0,
    text: "你好。",
    audioBase64: "AA==",
    format: "mp3",
  }]);
});

test("ignores old playback callbacks after a new turn owns controller state", () => {
  const actions: string[] = [];
  const controller = {
    currentTurnId: "new-turn",
    replyStarted: () => undefined,
    sentenceReady: (id: string) => actions.push(`ready:${id}`),
    sentencePlaybackFinished: (id: string) => actions.push(`played:${id}`),
    ttsFailed: (message: string) => actions.push(`failed:${message}`),
    replyFinished: () => actions.push("finished"),
  };
  const callbacks = createVoicePlaybackCallbacks(controller);

  callbacks.onStarted(itemForTurn("old-turn"));
  callbacks.onFinished(itemForTurn("old-turn"), null);
  callbacks.onError(itemForTurn("old-turn"), "old failed");
  callbacks.onDrained("old-turn");

  assert.deepEqual(actions, []);

  callbacks.onStarted(itemForTurn("new-turn"));
  callbacks.onFinished(itemForTurn("new-turn"), null);
  callbacks.onError(itemForTurn("new-turn"), "new failed");
  callbacks.onDrained("new-turn");

  assert.deepEqual(actions, [
    "ready:new-turn:0",
    "played:new-turn:0",
    "failed:new failed",
    "finished",
  ]);
});

function itemForTurn(turnId: string): VoicePlaybackItem {
  return {
    id: `${turnId}:0`,
    turnId,
    sessionKey: "role:mira",
    requestId: turnId,
    sequence: 0,
    text: "你好。",
    audioBase64: "AA==",
    format: "mp3",
  };
}
