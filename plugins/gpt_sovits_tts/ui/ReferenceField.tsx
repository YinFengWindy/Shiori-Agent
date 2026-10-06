import { useEffect, useRef, useState } from "react";
import { errorMessage, ghostButtonClass, inputClass, textareaClass, Select, usePluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { VoiceReference } from "../shared/contracts";
import { voiceLanguage, voiceLanguages } from "./languages";

/** Imports a private reference into this role's unsaved draft; transcription remains editable. */
export function ReferenceField({ title, roleId, client, value, disabled, onChange, onBusyChange }: {
  title: string; roleId: string; client: PluginRpcClient; value: VoiceReference | null; disabled: boolean; onChange(value: VoiceReference | null): void; onBusyChange(busy: boolean): void;
}) {
  const host = usePluginHostServices();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [duration, setDuration] = useState<number | null>(null);
  const revision = useRef(0);
  useEffect(() => { revision.current += 1; setDuration(null); return () => { revision.current += 1; }; }, [client, roleId]);
  async function importAudio() {
    const current = revision.current;
    setBusy(true); setError("");
    onBusyChange(true);
    try {
      const [source] = await host.pickFiles({ namespace: "gpt_sovits_tts-audio", filters: [{ name: "WAV 参考音频", extensions: ["wav"] }], maxFileBytes: 32 * 1024 * 1024 });
      if (!source || current !== revision.current) return;
      const reference = await client.call<{ asset: string; duration: number }>("reference.import", { role_id: roleId, source });
      if (current !== revision.current) return;
      onChange({ asset: reference.asset, prompt_text: value?.prompt_text ?? "", prompt_lang: value?.prompt_lang ?? "zh" });
      setDuration(reference.duration);
    } catch (cause) { if (current === revision.current) setError(errorMessage(cause)); }
    finally { if (current === revision.current) { setBusy(false); onBusyChange(false); } }
  }
  return <fieldset className="grid min-w-0 gap-3 rounded-md border border-line p-4" disabled={disabled || busy}>
    <legend className="px-1 text-body font-medium text-ink">{title}</legend>
    <div className="flex flex-wrap items-center gap-2">
      <button className={ghostButtonClass} onClick={() => void importAudio()}>{busy ? "导入中…" : value ? "更换音频" : "导入音频（3–10 秒）"}</button>
      {value ? <><span className="text-caption text-ink-muted">{duration === null ? "已导入" : `${duration.toFixed(1)} 秒`}</span><button className={ghostButtonClass} onClick={() => onChange(null)}>移除</button></> : null}
    </div>
    {error ? <host.ui.InlineError message={error} /> : null}
    {value ? <>
      <label className="grid gap-2">参考转写<textarea aria-label={`${title}参考转写`} className={textareaClass} rows={2} value={value.prompt_text} onChange={(event) => onChange({ ...value, prompt_text: event.target.value })} /></label>
      <label className="grid gap-2">参考语言<Select aria-label={`${title}参考语言`} disabled={disabled || busy} className={inputClass} value={value.prompt_lang} options={voiceLanguages} onValueChange={(next) => { const language = voiceLanguage(next); if (language) onChange({ ...value, prompt_lang: language }); }} /></label>
    </> : null}
  </fieldset>;
}
