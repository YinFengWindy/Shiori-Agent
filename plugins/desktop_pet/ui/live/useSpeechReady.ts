import { useEffect, useState } from "react";
import { errorMessage, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { speechOn, type VoicePreferences } from "../../background/voice/preferences";

type SpeechReadyState = { ready: boolean | null; error: string };

/**
 * Whether the pet speaks replies (voice on with a TTS provider), which a live
 * run needs. Re-read each time the dialog opens, since it is edited on the
 * plugin's settings page; null until the read answers or after it failed.
 */
export function useSpeechReady(client: PluginRpcClient, open: boolean) {
  const [state, setState] = useState<SpeechReadyState>({ ready: null, error: "" });
  useEffect(() => {
    if (!open) return undefined;
    let current = true;
    // An unchanged answer keeps the state object, so reopening re-renders nothing.
    const settle = (ready: boolean | null, error: string) => setState((prev) => prev.ready === ready && prev.error === error ? prev : { ready, error });
    client.call<VoicePreferences>("voice.preferences.get").then(
      (preferences) => { if (current) settle(speechOn(preferences), ""); },
      (cause: unknown) => { if (current) settle(null, errorMessage(cause)); },
    );
    return () => { current = false; };
  }, [client, open]);
  return state;
}
