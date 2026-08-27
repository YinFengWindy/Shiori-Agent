/** The input sources that can start a desktop-pet voice turn. */
export type VoiceInputSource = "pet" | "hotkey";

/** The delay that distinguishes a voice press from a pet drag or accidental click. */
export const VOICE_PRESS_THRESHOLD_MS = 300;

/** The maximum duration of one short-speech recording. */
export const VOICE_MAX_RECORDING_MS = 60_000;

/** The business states owned by the desktop voice controller. */
export type VoiceInteractionState =
  | { kind: "idle" }
  | { kind: "press_pending"; source: VoiceInputSource; startedAtMs: number }
  | { kind: "dragging" }
  | { kind: "recording"; source: VoiceInputSource; startedAtMs: number }
  | { kind: "transcribing" }
  | { kind: "sending" }
  | { kind: "waiting_reply" }
  | { kind: "speaking_prepare" }
  | { kind: "speaking"; sentenceId: string }
  | { kind: "finish_current_sentence_then_idle"; sentenceId: string }
  | { kind: "error"; message: string };

/** Events that advance one voice interaction without performing side effects. */
export type VoiceInteractionEvent =
  | { type: "press_started"; source: VoiceInputSource; atMs: number }
  | { type: "press_elapsed"; atMs: number }
  | { type: "pointer_moved" }
  | { type: "released" }
  | { type: "escape" }
  | { type: "recording_failed"; message: string }
  | { type: "recording_timed_out" }
  | { type: "asr_succeeded"; text: string }
  | { type: "asr_failed"; message: string }
  | { type: "chat_accepted" }
  | { type: "chat_failed"; message: string }
  | { type: "reply_started"; hasVoice: boolean }
  | { type: "sentence_ready"; sentenceId: string }
  | { type: "sentence_playback_finished"; sentenceId: string; nextSentenceId?: string }
  | { type: "reply_finished" }
  | { type: "new_input" }
  | { type: "reset" };

/** Returns the initial state for a desktop voice controller. */
export function createVoiceInteractionState(): VoiceInteractionState {
  return { kind: "idle" };
}

/** Returns whether the state owns an active voice task that must exclude microphone tests. */
export function isVoiceInteractionBusy(state: VoiceInteractionState): boolean {
  return state.kind !== "idle" && state.kind !== "dragging" && state.kind !== "error";
}

/**
 * Applies one event to the voice state machine.
 *
 * Stale events are ignored by returning the original state, which keeps bridge
 * and renderer teardown races from creating a second active voice task.
 */
export function transitionVoiceInteraction(
  state: VoiceInteractionState,
  event: VoiceInteractionEvent,
): VoiceInteractionState {
  switch (state.kind) {
    case "idle":
      if (event.type === "press_started") {
        return { kind: "press_pending", source: event.source, startedAtMs: event.atMs };
      }
      return state;
    case "press_pending":
      if (event.type === "press_elapsed" && event.atMs - state.startedAtMs >= VOICE_PRESS_THRESHOLD_MS) {
        return { kind: "recording", source: state.source, startedAtMs: state.startedAtMs };
      }
      if (event.type === "pointer_moved") {
        return { kind: "dragging" };
      }
      if (event.type === "released" || event.type === "escape") {
        return { kind: "idle" };
      }
      return state;
    case "dragging":
      if (event.type === "released" || event.type === "escape" || event.type === "reset") {
        return { kind: "idle" };
      }
      return state;
    case "recording":
      if (event.type === "released" || event.type === "recording_timed_out") {
        return { kind: "transcribing" };
      }
      if (event.type === "escape") {
        return { kind: "idle" };
      }
      if (event.type === "recording_failed") {
        return { kind: "error", message: event.message };
      }
      return state;
    case "transcribing":
      if (event.type === "asr_succeeded") {
        return event.text.trim() ? { kind: "sending" } : { kind: "error", message: "没有听清，请重试" };
      }
      if (event.type === "recording_failed") {
        return { kind: "error", message: event.message };
      }
      if (event.type === "asr_failed") {
        return { kind: "error", message: event.message };
      }
      if (event.type === "escape" || event.type === "new_input" || event.type === "reset") {
        return { kind: "idle" };
      }
      return state;
    case "sending":
      if (event.type === "chat_accepted") {
        return { kind: "waiting_reply" };
      }
      if (event.type === "chat_failed") {
        return { kind: "error", message: event.message };
      }
      if (event.type === "escape" || event.type === "new_input" || event.type === "reset") {
        return { kind: "idle" };
      }
      return state;
    case "waiting_reply":
      if (event.type === "reply_started") {
        return event.hasVoice ? { kind: "speaking_prepare" } : { kind: "idle" };
      }
      if (event.type === "escape" || event.type === "reply_finished" || event.type === "new_input" || event.type === "reset") {
        return { kind: "idle" };
      }
      return state;
    case "speaking_prepare":
      if (event.type === "sentence_ready") {
        return { kind: "speaking", sentenceId: event.sentenceId };
      }
      if (event.type === "escape" || event.type === "reply_finished" || event.type === "new_input" || event.type === "reset") {
        return { kind: "idle" };
      }
      return state;
    case "speaking":
      if (event.type === "sentence_playback_finished" && event.sentenceId === state.sentenceId) {
        return event.nextSentenceId
          ? { kind: "speaking", sentenceId: event.nextSentenceId }
          : { kind: "speaking_prepare" };
      }
      if (event.type === "new_input") {
        return { kind: "finish_current_sentence_then_idle", sentenceId: state.sentenceId };
      }
      if (event.type === "reply_finished" || event.type === "reset") {
        return { kind: "idle" };
      }
      return state;
    case "finish_current_sentence_then_idle":
      if (event.type === "sentence_playback_finished" && event.sentenceId === state.sentenceId) {
        return { kind: "idle" };
      }
      if (event.type === "reset") {
        return { kind: "idle" };
      }
      return state;
    case "error":
      return event.type === "reset" || event.type === "new_input" ? { kind: "idle" } : state;
  }
}
