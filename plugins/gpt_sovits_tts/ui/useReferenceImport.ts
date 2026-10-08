import { useState } from "react";
import { errorMessage, usePluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";

/** An imported, provider-owned reference audio before it joins the role voice. */
export type ImportedReference = { asset: string; duration: number };

/**
 * Picks one WAV and imports it as this role's private reference. `busy` names
 * the mood being imported (the empty mood is the default reference); a
 * cancelled picker or a failure resolves null, so the caller adds nothing.
 */
export function useReferenceImport(client: PluginRpcClient, roleId: string) {
  const host = usePluginHostServices();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function importFor(mood: string): Promise<ImportedReference | null> {
    setBusy(mood);
    setError("");
    try {
      const [source] = await host.pickFiles({ namespace: "gpt_sovits_tts-audio", filters: [{ name: "WAV 参考音频", extensions: ["wav"] }], maxFileBytes: 32 * 1024 * 1024 });
      if (!source) return null;
      return await client.call<ImportedReference>("reference.import", { role_id: roleId, source });
    } catch (cause) {
      setError(errorMessage(cause));
      return null;
    } finally {
      setBusy(null);
    }
  }

  return { busy, error, importFor };
}
