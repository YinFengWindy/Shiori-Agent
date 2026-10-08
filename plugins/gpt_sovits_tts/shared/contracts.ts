/** GPT-SoVITS settings persisted in this provider's private document. */
export type GptSoVitsSettings = { connection_mode: "external" | "managed"; url: string; version: "v2ProPlus"; gpt_weights: string; sovits_weights: string };

/** Supported api_v2 language identifiers for the selected model generation. */
export type VoiceLanguage = "auto" | "auto_yue" | "zh" | "en" | "ja" | "ko" | "yue" | "all_zh" | "all_ja" | "all_ko" | "all_yue";

/** A provider-owned audio identifier, its reference transcription and the seconds measured at import (null for older references). */
export type VoiceReference = { asset: string; prompt_text: string; prompt_lang: VoiceLanguage; duration?: number | null };

/** Private role voice document; it never enters the host role draft. */
export type RoleVoice = { text_lang: VoiceLanguage; speed: number; default: VoiceReference | null; moods: Record<string, VoiceReference> };

/** Reachability does not verify loaded model identity or recover an uncertain inference. */
export type GptSoVitsHealth = { reachable: boolean; configured_version: "v2ProPlus"; model_verified: false; busy: boolean; recovery_required: boolean; instance: { operation: string; url: string; state: "in_flight" | "unknown"; managed?: { generation: string; runtime: string } } | null };

/** Preview work is identified separately from renderer mount and role identity. */
export type PreviewState = { id: string; role_id: string; phase: "idle" | "generating" | "playing" | "error"; error: string };
