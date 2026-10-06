import { useEffect, useState } from "react";
import { ghostButtonClass, inputClass, Select, usePluginHostServices, usePrivateDraft, type PluginRoleUiProps } from "@yinfengwindy/shiori-sdk";
import type { RoleVoice } from "../shared/contracts";
import { voiceLanguage, voiceLanguages } from "./languages";
import { ReferenceField } from "./ReferenceField";
import { PreviewControls } from "./PreviewControls";
import { EmotionReferences } from "./EmotionReferences";
import { updateEmotionReference } from "./emotionReferenceState";

/** Owns private role references, dirty state and explicit save without changing the host role. */
export function RoleVoiceEditor({ roleId, role, client, disabled, onDirtyChange }: PluginRoleUiProps) {
  const host = usePluginHostServices();
  const state = usePrivateDraft(client, roleId, {
    load: () => client.call<RoleVoice>("role.get", { role_id: roleId }),
    save: (voice) => client.call<RoleVoice>("role.set", { role_id: roleId, voice }),
  });
  const [pendingNames, setPendingNames] = useState<{ roleId: string | null; dirty: boolean }>({ roleId, dirty: false });
  const hasPendingNames = pendingNames.roleId === roleId && pendingNames.dirty;
  const dirty = state.dirty || hasPendingNames;
  useEffect(() => { onDirtyChange(dirty); }, [dirty, onDirtyChange]);
  const [imports, setImports] = useState<Set<string>>(() => new Set());
  useEffect(() => { setImports(new Set()); }, [roleId]);
  const importing = (key: string, busy: boolean) => setImports((current) => {
    const next = new Set(current);
    if (busy) next.add(key); else next.delete(key);
    return next;
  });
  const draft = state.draft;
  const moods = Object.keys(draft?.moods ?? {});
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
      <EmotionReferences key={`emotions:${roleId}`} roleId={roleId} client={client} moods={draft.moods} suggestions={role?.moodCatalog ?? []} disabled={blocked || imports.size > 0} onBusyChange={(name, busy) => importing(`mood:${name}`, busy)} onPendingChange={(value) => setPendingNames((current) => current.roleId === roleId && current.dirty === value ? current : { roleId, dirty: value })} onChange={(name, value) => state.setDraft((current) => current ? { ...current, moods: updateEmotionReference(current.moods, name, value) } : current)} />
      <div className="flex items-center justify-end gap-3">
        {dirty ? <span className="text-caption text-ink-muted">未保存</span> : null}
        <button className={ghostButtonClass} disabled={blocked || imports.size > 0 || hasPendingNames || !state.dirty} onClick={() => void state.save()}>{state.saving ? "保存中…" : "保存声音设置"}</button>
      </div>
      <PreviewControls key={`preview:${roleId}`} client={client} roleId={roleId} moods={moods} disabled={blocked || imports.size > 0 || dirty || !draft.default} />
    </> : null}
  </section>;
}
