import { useEffect, useRef, useState } from "react";
import { compactGhostButtonClass, errorMessage, SettingsField, SettingsGroup, settingsInputClass, type PluginInjectedProps } from "@yinfengwindy/shiori-sdk";
import { rpcMethods } from "../rpcMethods.generated";

/** Upload one explicitly selected WAV, without recording or sending a chat turn. */
export function TranscriptionTest({ client, host }: PluginInjectedProps) {
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const revision = useRef(0);
  useEffect(() => {
    const retire = () => { revision.current++; };
    retire();
    return retire;
  }, [client]);
  async function transcribe() {
    const current = revision.current;
    setBusy(true); setError("");
    try {
      const [source] = await host.pickFiles({ namespace: "fish_audio-audio", filters: [{ name: "WAV 音频", extensions: ["wav"] }], maxFileBytes: 32 * 1024 * 1024 });
      if (!source || current !== revision.current) return;
      const result = await client.call<{ text: string }>(rpcMethods["transcribe_file"], { source }, { timeoutMs: 95_000 });
      if (current === revision.current) setText(result.text);
    } catch (cause) { if (current === revision.current) setError(errorMessage(cause)); }
    finally { if (current === revision.current) setBusy(false); }
  }
  return <SettingsGroup title="转写测试">
    <SettingsField label="WAV 文件"><button type="button" className={compactGhostButtonClass} disabled={busy} onClick={() => void transcribe()}>{busy ? "识别中…" : "选择 WAV 并转写"}</button></SettingsField>
    <SettingsField label="转写结果" layout="stack">
      {error ? <host.ui.InlineError message={error} /> : null}
      <textarea aria-label="Fish Audio 转写结果" className={settingsInputClass} value={text} readOnly rows={4} />
    </SettingsField>
  </SettingsGroup>;
}
