import { useEffect, useState } from "react";
import { ghostButtonClass, inputClass, useLatestRef, usePluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { VoiceReference } from "../shared/contracts";
import { emotionNameError } from "./emotionReferenceState";
import { ReferenceField } from "./ReferenceField";

/** Owns unimported mapping names while saved references stay in the provider's role draft. */
export function EmotionReferences({ roleId, client, moods, suggestions, disabled, onChange, onBusyChange, onPendingChange }: {
  roleId: string; client: PluginRpcClient; moods: Record<string, VoiceReference>; suggestions: readonly string[]; disabled: boolean;
  onChange(name: string, value: VoiceReference | null): void; onBusyChange(name: string, busy: boolean): void; onPendingChange(pending: boolean): void;
}) {
  const host = usePluginHostServices();
  const [name, setName] = useState("");
  const [pending, setPending] = useState<string[]>([]);
  const [error, setError] = useState("");
  const report = useLatestRef(onPendingChange);
  const names = [...new Set([...Object.keys(moods), ...pending])];
  const offered = [...new Set(suggestions.map((value) => value.trim()))].filter((value) => !emotionNameError(value, names));
  useEffect(() => { report.current(pending.length > 0); }, [report, pending.length]);
  function add(raw: string) {
    const failure = emotionNameError(raw, names);
    setError(failure);
    if (failure) return;
    setPending((current) => [...current, raw.trim()]);
    setName("");
  }
  function update(key: string, reference: VoiceReference | null) {
    onChange(key, reference);
    setPending((current) => current.filter((value) => value !== key));
  }
  return <section className="grid gap-3" aria-label="情绪参考">
    <div className="flex flex-wrap items-end gap-2">
      <label className="grid flex-1 gap-2">情绪名称<input aria-label="情绪名称" className={inputClass} disabled={disabled} value={name} onChange={(event) => setName(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); add(name); } }} /></label>
      <button className={ghostButtonClass} disabled={disabled} onClick={() => add(name)}>添加情绪</button>
    </div>
    {offered.length ? <div className="flex flex-wrap items-center gap-2"><span className="text-caption text-ink-muted">角色情绪</span>{offered.map((value) => <button key={value} className={ghostButtonClass} disabled={disabled} onClick={() => add(value)}>{value}</button>)}</div> : null}
    {error ? <host.ui.InlineError message={error} /> : null}
    <div className="grid gap-3 sm:grid-cols-2">
      {names.map((key) => <div key={key} className="grid content-start gap-2">
        <ReferenceField title={key} roleId={roleId} client={client} value={Object.hasOwn(moods, key) ? moods[key] : null} disabled={disabled} onBusyChange={(busy) => onBusyChange(key, busy)} onChange={(reference) => update(key, reference)} />
        <div className="justify-self-end"><button className={ghostButtonClass} disabled={disabled} aria-label={`删除情绪 ${key}`} onClick={() => update(key, null)}>删除情绪</button></div>
      </div>)}
    </div>
  </section>;
}
