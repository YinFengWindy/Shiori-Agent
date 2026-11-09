import type { PluginBackgroundSettled, PluginServiceReference } from "@yinfengwindy/shiori-sdk";

/** Shared model-provider discovery contract. */
export const petModelsContract = "shiori.pet-models.v1";
/** Stable role-owned selection; format data stays with the provider. */
export type PetModelReference = { provider: PluginServiceReference; model_id: string };
/** A provider-neutral model description. */
export type PetModel = { id: string; display_name: string; preview_abs?: string | null; body: { width: number; height: number }; actions: string[] };
/** One resolved role and its selected model. */
export type PetBinding = { role_id: string; provider: PluginServiceReference; model: PetModel };
/** Pet-owned reply presentation. */
export type PetReplyBubble = { text: string; paused: boolean; persistent: boolean };
/** Stable empty reply. */
export const emptyPetReply: PetReplyBubble = { text: "", paused: false, persistent: false };
/** Voice states shared by every presentation format. */
export type PetVoiceState = {
  status: "idle" | "press_pending" | "dragging" | "recording" | "transcribing" | "sending" | "waiting_reply" | "speaking_prepare" | "speaking" | "error";
  source?: "surface" | "hotkey";
  message?: string;
};
/** Retained business presentation; animation state remains provider-local. */
export type PetPresentationState = { reply: PetReplyBubble; voice: PetVoiceState };
/** Every request/report identifies the exact model instance, including stale work. */
export type PetPresentationIdentity = { request_id: string; lease_id: string; role_id: string; model_id: string };
/** Generic movement and model-declared action names. */
export type PetAction = { kind: "play"; name: string } | { kind: "move"; target: "top_left" | "top_right" | "center" | "bottom_left" | "bottom_right"; animation?: "" | "run" };
/** Short service requests; acceptance never means the model has loaded. */
export type PetPresentationRequest = PetPresentationIdentity & {
  op: "prepare" | "show" | "hide" | "update" | "action" | "close";
  state?: PetPresentationState;
  position?: { x: number; y: number };
  command?: PetAction;
};
/** Interaction requests are interpreted by desktop_pet, never the renderer provider. */
export type PetGesture = { kind: "voice.gesture"; gesture: "press" | "move" | "release" | "cancel" } | { kind: "voice.stop" | "hide" | "bubble.dismiss" };
/** Provider completion and interaction reports. */
export type PetProviderReport = PetPresentationIdentity & {
  kind: "ready" | "shown" | "hidden" | "closed" | "settled" | "gesture" | "failed" | "lost";
  error?: string;
  placement?: PluginBackgroundSettled;
  gesture?: PetGesture;
};

/** Stable selection identity without separator collisions. */
export function petModelKey(value: PetModelReference): string { return JSON.stringify([value.provider.plugin_id, value.provider.service_id, value.model_id]); }
/** Validates a persisted or wire model reference. */
export function readPetModelReference(value: unknown): PetModelReference | null {
  if (!isRecord(value) || !nonempty(value.model_id)) return null;
  const provider = readPetProviderReference(value.provider);
  return provider ? { provider, model_id: value.model_id } : null;
}
/** Validates a public service identity without inventing a model reference. */
export function readPetProviderReference(value: unknown): PluginServiceReference | null {
  return isRecord(value) && nonempty(value.plugin_id) && nonempty(value.service_id) ? { plugin_id: value.plugin_id, service_id: value.service_id } : null;
}
/** Checks unknown JSON objects at plugin boundaries. */
export function isRecord(value: unknown): value is Record<string, unknown> { return Boolean(value && typeof value === "object" && !Array.isArray(value)); }
/** Checks nonempty identity fields without coercion. */
export function nonempty(value: unknown): value is string { return typeof value === "string" && value.trim().length > 0; }
/** Parses the common command identity before dispatching any effects. */
export function readPresentationIdentity(value: unknown): PetPresentationIdentity | null {
  if (!isRecord(value) || !nonempty(value.request_id) || !nonempty(value.lease_id) || !nonempty(value.role_id) || !nonempty(value.model_id)) return null;
  return { request_id: value.request_id, lease_id: value.lease_id, role_id: value.role_id, model_id: value.model_id };
}
/** Parses retained reply/voice state without inventing missing business data. */
export function readPresentationState(value: unknown): PetPresentationState | null {
  if (!isRecord(value) || !isRecord(value.reply) || !isRecord(value.voice)) return null;
  const { reply, voice } = value;
  const states = ["idle", "press_pending", "dragging", "recording", "transcribing", "sending", "waiting_reply", "speaking_prepare", "speaking", "error"] as const;
  const status = states.find((state) => state === voice.status);
  if (typeof reply.text !== "string" || typeof reply.paused !== "boolean" || typeof reply.persistent !== "boolean" || !status) return null;
  return { reply: { text: reply.text, paused: reply.paused, persistent: reply.persistent }, voice: { status, ...(voice.source === "surface" || voice.source === "hotkey" ? { source: voice.source } : {}), ...(typeof voice.message === "string" ? { message: voice.message } : {}) } };
}
