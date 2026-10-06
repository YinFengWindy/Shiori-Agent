import { useEffect, useRef, useState } from "react";
import { errorMessage, ghostButtonClass, textareaClass, type PluginInjectedProps } from "@yinfengwindy/shiori-sdk";

/** Tests this ASR provider with an explicitly selected WAV, independently of a desktop pet. */
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
  return <section className="grid gap-3">
    <h3 className="text-body font-medium text-ink">文件转写</h3>
    <div><button className={ghostButtonClass} disabled={busy} onClick={() => void transcribe()}>{busy ? "识别中…" : "选择 WAV 并转写"}</button></div>
    {error ? <host.ui.InlineError message={error} /> : null}
    <textarea aria-label="转写结果" className={textareaClass} value={text} readOnly rows={4} />
  </section>;
}
