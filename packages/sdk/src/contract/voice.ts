/** Voice state emitted by the host and injected into an owning surface. */
export type VoiceInputSource = "surface" | "hotkey";

/** Current host-owned voice state presented by the receiving surface. */
export type VoiceStatePayload = {
  status:
    | "idle"
    | "press_pending"
    | "dragging"
    | "recording"
    | "transcribing"
    | "sending"
    | "waiting_reply"
    | "speaking_prepare"
    | "speaking"
    | "finish_current_sentence_then_idle"
    | "error";
  source?: VoiceInputSource;
  message?: string;
};
