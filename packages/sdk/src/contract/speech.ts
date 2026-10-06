/** Public ASR service contract: shiori.asr.v1. */
export type AsrRequest = { audio_base64: string; format: "wav" };
/** Recognized text returned by an ASR provider. */
export type AsrResult = { text: string };
/** Public TTS service contract: shiori.tts.v1; providers own their role settings. */
export type TtsRequest = { text: string; role_id: string; mood: string };
/** Complete audio returned by a TTS provider. */
export type TtsResult = { audio_base64: string; format: "wav" | "mp3" };
