/** Global connection settings, with no returned API secret. */
export type FishSettings = { tts_model: "s2.1-pro-free" | "s2.1-pro" | "s2-pro"; has_api_key: boolean };
/** Fish text normalization language; auto leaves per-chunk detection to the API. */
export type TextLanguage = "auto" | "zh-CN" | "zh-TW" | "en" | "ja" | "ko" | "es-ES" | "es-MX" | "fr" | "de" | "it" | "pt-BR" | "ru" | "ar" | "tr" | "fil";
/** A role's private voice mapping. */
export type RoleVoice = { reference_id: string; speed: number; language: TextLanguage };
/** A preview identifies its editor so a stale stop cannot stop newer playback. */
export type PreviewState = { id: string; phase: "idle" | "generating" | "playing" | "error"; error: string };
