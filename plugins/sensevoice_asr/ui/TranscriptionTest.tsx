import { useEffect, useRef, useState } from "react";
import { compactGhostButtonClass, errorMessage, SettingsField, SettingsGroup, settingsInputClass, type PluginInjectedProps } from "@yinfengwindy/shiori-sdk";

/** The 「转写测试」 group: tests this ASR provider with an explicitly selected WAV, independently of a desktop pet. */
export function TranscriptionTest({ client, host }: PluginInjectedProps) {
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const revision = useRef(0);
  useEffect(() => { revision.current += 1; return () => { revision.current += 1; }; }, [client]);
  async function transcribe() {
    const current = revision.current;
    setBusy(true);
    setError("");
    try {
      const [source] = await host.pickFiles({ namespace: "sensevoice_asr-audio", filters: [{ name: "WAV 音频", extensions: ["wav"] }], maxFileBytes: 32 * 1024 * 1024 });
      if (!source || current !== revision.current) return;
      const result = await client.call<{ text: string }>("transcribe_file", { source }, { timeoutMs: 65_000 });
      if (current === revision.current) setText(result.text);
    } catch (cause) {
      if (current === revision.current) setError(errorMessage(cause));
    } finally {
      if (current === revision.current) setBusy(false);
    }
  }
  return <SettingsGroup title="转写测试">
    <SettingsField label="WAV 文件">
      <div className="flex xl:justify-end"><button type="button" className={compactGhostButtonClass} disabled={busy} onClick={() => void transcribe()}>{busy ? "识别中…" : "选择 WAV 并转写"}</button></div>
    </SettingsField>
    <SettingsField label="转写结果" layout="stack">
      <div className="grid gap-3">
        {error ? <host.ui.InlineError message={error} /> : null}
        <textarea aria-label="转写结果" className={settingsInputClass} value={text} readOnly rows={4} />
      </div>
    </SettingsField>
  </SettingsGroup>;
}
