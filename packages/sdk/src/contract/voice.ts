/**
 * Public voice state pushed to the desktop pet's surface (and the host's own
 * settings UI). Voice input is still a host feature (#221), so this is a host
 * push the pet renders, not a plugin capability.
 */
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
  source?: "pet" | "hotkey";
  message?: string;
};
