import { useEffect, useState } from "react";
import { ghostButtonClass, inputClass, Select, usePluginHostServices, usePrivateDraft, type PluginRoleUiProps } from "@yinfengwindy/shiori-sdk";
import type { RoleVoice } from "../shared/contracts";
import { voiceLanguage, voiceLanguages } from "./languages";
import { ReferenceField } from "./ReferenceField";
import { PreviewControls } from "./PreviewControls";

/** Owns private role references, dirty state and explicit save without changing the host role. */
export function RoleVoiceEditor({ roleId, role, client, disabled, onDirtyChange }: PluginRoleUiProps) {
  const host = usePluginHostServices();
  const state = usePrivateDraft(client, roleId, {
    load: () => client.call<RoleVoice>("role.get", { role_id: roleId }),
    save: (voice) => client.call<RoleVoice>("role.set", { role_id: roleId, voice }),
    onDirtyChange,
  });
  const [imports, setImports] = useState<Set<string>>(() => new Set());
  useEffect(() => { setImports(new Set()); }, [roleId]);
  const importing = (key: string, busy: boolean) => setImports((current) => {
    const next = new Set(current);
    if (busy) next.add(key); else next.delete(key);
    return next;
  });
  const draft = state.draft;
  const moods = [...new Set([...(role?.moodCatalog ?? []), ...Object.keys(draft?.moods ?? {})])].filter(Boolean);
  const blocked = disabled || state.saving;
  return <section className="grid gap-4">
    <h2 className="text-title font-semibold text-ink">GPT-SoVITS 声音</h2>
    {!roleId ? <p className="m-0 text-body text-ink-muted">请先保存角色</p> : null}
    {state.loading ? <span className="text-ink-muted">正在读取声音设置…</span> : null}
    {state.error ? <host.ui.InlineError message={state.error} /> : null}
    {roleId && draft ? <>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-2">文本语言<Select aria-label="文本语言" className={inputClass} disabled={blocked} value={draft.text_lang} options={voiceLanguages} onValueChange={(next) => { const language = voiceLanguage(next); if (language) state.setDraft({ ...draft, text_lang: language }); }} /></label>
        <label className="grid gap-2">语速<input aria-label="语速" className={inputClass} disabled={blocked} type="number" min="0.5" max="2" step="0.1" value={draft.speed} onChange={(event) => state.setDraft({ ...draft, speed: Number(event.target.value) })} /></label>
      </div>
      <ReferenceField title="默认参考" roleId={roleId} client={client} value={draft.default} disabled={blocked} onBusyChange={(busy) => importing("default", busy)} onChange={(value) => state.setDraft((current) => current ? { ...current, default: value } : current)} />
      <div className="grid gap-3 sm:grid-cols-2">
        {moods.map((mood) => <ReferenceField key={mood} title={mood} roleId={roleId} client={client} value={draft.moods[mood] ?? null} disabled={blocked} onBusyChange={(busy) => importing(`mood:${mood}`, busy)} onChange={(value) => state.setDraft((current) => {
          if (!current) return current;
          const next = { ...current.moods };
          if (value) next[mood] = value; else delete next[mood];
          return { ...current, moods: next };
        })} />)}
      </div>
      <div className="flex items-center justify-end gap-3">
        {state.dirty ? <span className="text-caption text-ink-muted">未保存</span> : null}
        <button className={ghostButtonClass} disabled={blocked || imports.size > 0 || !state.dirty} onClick={() => void state.save()}>{state.saving ? "保存中…" : "保存声音设置"}</button>
      </div>
      <PreviewControls key={roleId} client={client} roleId={roleId} moods={moods} disabled={blocked || imports.size > 0 || state.dirty || !draft.default} />
    </> : null}
  </section>;
}
