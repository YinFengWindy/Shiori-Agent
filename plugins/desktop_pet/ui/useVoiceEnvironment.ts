import { useEffect, useState } from "react";
import { errorMessage, type NativeAudioDevice, type PluginRpcClient, type PluginServiceDescriptor } from "@yinfengwindy/shiori-sdk";
import type { VoiceProviderKind } from "./voiceSettingsModel";

/** Installed providers per kind. */
export type VoiceProviderLists = Record<VoiceProviderKind, PluginServiceDescriptor[]>;

type ScopedRead<T> = { source: PluginRpcClient | null; value: T | null; error: string };

/**
 * Reads one list for the current client. Each list keeps its own error, so a
 * failed device listing never blocks the providers or the preferences.
 * `read` must be a stable (module-level) function.
 */
function useClientRead<T>(client: PluginRpcClient, read: (client: PluginRpcClient) => Promise<T>) {
  const [state, setState] = useState<ScopedRead<T>>({ source: null, value: null, error: "" });
  useEffect(() => {
    let active = true;
    read(client).then(
      (value) => { if (active) setState({ source: client, value, error: "" }); },
      (cause: unknown) => { if (active) setState({ source: client, value: null, error: errorMessage(cause) }); },
    );
    return () => { active = false; };
  }, [client, read]);
  // Another client's answer is never shown while this one's is pending.
  return state.source === client ? state : { source: client, value: null, error: "" };
}

async function readProviders(client: PluginRpcClient): Promise<VoiceProviderLists> {
  const [asr, tts] = await Promise.all([client.services.list("shiori.asr.v1"), client.services.list("shiori.tts.v1")]);
  return { asr: asr.services, tts: tts.services };
}

function readDevices(client: PluginRpcClient) {
  return client.background.call<NativeAudioDevice[]>("voice.devices");
}

/** The installed speech providers and the microphones the voice settings choose from. */
export function useVoiceEnvironment(client: PluginRpcClient) {
  const providers = useClientRead(client, readProviders);
  const devices = useClientRead(client, readDevices);
  return {
    providers: providers.value,
    providersError: providers.error,
    devices: devices.value ?? [],
    devicesError: devices.error,
  };
}
