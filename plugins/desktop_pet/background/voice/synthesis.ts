import type { BackgroundCtx, PluginServiceReference, TtsResult } from "@yinfengwindy/shiori-sdk";

/** One sentence to speak in a role's voice; `mood` is empty when the caller has none. */
export type SpeechRequest = { text: string; roleId: string; mood: string };

/** The one place the pet builds a TTS `synthesize` call, shared by chat and live speech. */
export function synthesizeSentence(rpc: Pick<BackgroundCtx["rpc"], "services">, provider: PluginServiceReference, request: SpeechRequest) {
  return rpc.services.call<TtsResult>(provider, "synthesize", { text: request.text, role_id: request.roleId, mood: request.mood });
}
