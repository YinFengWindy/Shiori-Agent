import { useEffect, useRef, useState } from "react";
import { errorMessage, ghostButtonClass, inputClass, type PluginSettingsSectionComponentProps } from "@yinfengwindy/shiori-sdk";
import type { SenseVoiceHealth, SenseVoiceSettings } from "./contract";
import { TranscriptionTest } from "./TranscriptionTest";

/** Owns SenseVoice connection edits and reports actual service readiness. */
export function SenseVoiceSettingsPage({ client, host }: PluginSettingsSectionComponentProps) {
  const [draft, setDraft] = useState<SenseVoiceSettings | null>(null);
  const [saved, setSaved] = useState<SenseVoiceSettings | null>(null);
  const [health, setHealth] = useState<SenseVoiceHealth | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const revision = useRef(0);
  useEffect(() => {
    const current = ++revision.current;
    void client.call<SenseVoiceSettings>("settings.get").then((value) => {
      if (current === revision.current) { setDraft(value); setSaved(value); }
    }).catch((cause) => { if (current === revision.current) setError(errorMessage(cause)); });
    return () => { revision.current += 1; };
  }, [client]);
  async function run(action: "save" | "health") {
    if (!draft) return;
    const current = revision.current;
    setBusy(true); setError("");
    try {
      if (action === "save") {
        const value = await client.call<SenseVoiceSettings>("settings.set", draft);
        if (current === revision.current) { setDraft(value); setSaved(value); setHealth(null); }
      } else {
        const value = await client.call<SenseVoiceHealth>("health");
        if (current === revision.current) setHealth(value);
      }
    } catch (cause) { if (current === revision.current) setError(errorMessage(cause)); }
    finally { if (current === revision.current) setBusy(false); }
  }
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved);
  return <div className="grid gap-6">
    {error ? <host.ui.InlineError message={error} /> : null}
    {draft ? <section className="grid gap-3">
      <label className="grid gap-2">服务地址<input aria-label="SenseVoice 服务地址" className={inputClass} value={draft.url} disabled={busy} onChange={(event) => setDraft({ ...draft, url: event.target.value })} /></label>
      <div className="flex gap-4 text-body-sm text-ink-muted"><span>SenseVoiceSmall</span><span>CPU</span></div>
      <div className="flex gap-2">
        <button className={ghostButtonClass} disabled={busy || !dirty} onClick={() => void run("save")}>保存</button>
        <button className={ghostButtonClass} disabled={busy || dirty} onClick={() => void run("health")}>检查连接</button>
      </div>
      {health ? <p role="status" className="m-0 text-body-sm text-ink-secondary">{health.ready ? "服务就绪" : "服务未就绪"} · {health.model} · {health.device}</p> : null}
    </section> : error ? null : <span className="text-ink-muted">正在读取设置…</span>}
    <TranscriptionTest client={client} host={host} />
  </div>;
}
