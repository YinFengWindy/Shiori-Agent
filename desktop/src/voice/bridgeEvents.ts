import type { BridgeEvent } from "../shared.js";
import type { VoiceBridge } from "./controller.js";
import type { VoicePlaybackCallbacks, VoicePlaybackItem } from "./playback.js";

export interface VoiceTurnPlaybackSelection {
  /** Selects the turn whose newly arriving sentences may enter playback. */
  beginTurn(turnId: string): void;
}

export interface VoiceTurnEventController {
  readonly currentTurnId: string | null;
  replyStarted(hasVoice: boolean): void;
  sentenceReady(sentenceId: string): void;
  ttsFailed(message: string): void;
}

export interface VoicePlaybackEventController extends VoiceTurnEventController {
  sentencePlaybackFinished(sentenceId: string, nextSentenceId?: string): void;
  replyFinished(): void;
}

export interface VoiceTurnPlaybackQueue {
  enqueue(item: VoicePlaybackItem): void;
  finishTurn(turnId: string): void;
}

/** Routes hidden-player callbacks only when their turn still owns controller state. */
export function createVoicePlaybackCallbacks(
  controller: VoicePlaybackEventController,
): VoicePlaybackCallbacks {
  return {
    onStarted: (item) => {
      if (item.turnId === controller.currentTurnId) controller.sentenceReady(item.id);
    },
    onFinished: (item, nextItem) => {
      if (item.turnId === controller.currentTurnId) {
        controller.sentencePlaybackFinished(item.id, nextItem?.id);
      }
    },
    onError: (item, message) => {
      if (item.turnId === controller.currentTurnId) controller.ttsFailed(message);
    },
    onDrained: (turnId) => {
      if (turnId === controller.currentTurnId) controller.replyFinished();
    },
  };
}

/** Selects a new local playback turn and retires the previous backend turn. */
export async function selectVoiceTurn(
  bridge: VoiceBridge,
  playback: VoiceTurnPlaybackSelection,
  previousTurnId: string | null,
  nextTurnId: string,
): Promise<void> {
  playback.beginTurn(nextTurnId);
  if (!previousTurnId) return;
  await cancelVoiceTurn(bridge, previousTurnId);
}

/** Cancels one backend voice turn after its local playback ownership is retired. */
export async function cancelVoiceTurn(bridge: VoiceBridge, turnId: string): Promise<void> {
  const response = await bridge.invoke({
    method: "voice.turn.cancel",
    payload: { voice_turn_id: turnId },
  });
  if (response.error) {
    throw new Error(response.error.message);
  }
}

/** Routes current-turn voice events and ignores every late event from retired turns. */
export function handleVoiceBridgeEvent(
  event: BridgeEvent,
  controller: VoiceTurnEventController,
  playback: VoiceTurnPlaybackQueue,
): boolean {
  if (![
    "voice.reply.started",
    "voice.tts.audio",
    "voice.tts.error",
    "voice.tts.finished",
  ].includes(event.method)) {
    return false;
  }
  const turnId = String(event.payload.voice_turn_id || "").trim();
  if (!turnId || turnId !== controller.currentTurnId) return true;
  if (event.method === "voice.reply.started") {
    controller.replyStarted(Boolean(event.payload.has_voice));
    return true;
  }
  if (event.method === "voice.tts.error") {
    controller.ttsFailed(String(event.payload.message || "角色语音合成失败"));
    return true;
  }
  if (event.method === "voice.tts.finished") {
    playback.finishTurn(turnId);
    return true;
  }
  const requestId = String(event.payload.request_id || event.id || "");
  const sequence = Number(event.payload.sequence);
  const audioBase64 = String(event.payload.audio_base64 || "");
  if (!requestId || !Number.isInteger(sequence) || !audioBase64) return true;
  const itemId = `${requestId}:${sequence}`;
  controller.sentenceReady(itemId);
  playback.enqueue({
    id: itemId,
    turnId,
    sessionKey: String(event.payload.session_key || ""),
    requestId,
    sequence,
    text: String(event.payload.text || ""),
    audioBase64,
    format: "mp3",
  });
  return true;
}
