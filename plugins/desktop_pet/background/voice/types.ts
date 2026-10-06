/** Voice state owned by the desktop pet and presented on its own surface. */
export type VoiceInputSource = "surface" | "hotkey";

/** Current plugin-owned voice state presented by the receiving surface. */
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
    | "error";
  source?: VoiceInputSource;
  message?: string;
};
