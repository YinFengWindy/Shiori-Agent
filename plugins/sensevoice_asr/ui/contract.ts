/** Connection settings persisted privately by SenseVoiceSmall. */
export type SenseVoiceSettings = { connection_mode: "external" | "managed"; url: string; device: "cpu"; model: "sensevoice" };

/** Loaded service information, distinct from transcription quality. */
export type SenseVoiceHealth = { device: string; model: string; ready: boolean };
