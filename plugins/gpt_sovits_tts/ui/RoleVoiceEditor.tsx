import { compactGhostButtonClass, inputClass, Select, usePluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { voiceLanguage, voiceLanguages } from "./languages";
import { PreviewControls } from "./PreviewControls";
import { ReferenceList } from "./ReferenceList";
import type { RoleVoiceAutosave } from "./useRoleVoice";
import { useSavedPreview } from "./useSavedPreview";

type RoleVoiceEditorProps = {
  roleId: string | null;
  client: PluginRpcClient;
  voice: RoleVoiceAutosave;
  moodCatalog: readonly string[];
  disabled: boolean;
};

/**
 * The GPT-SoVITS card's dialog: the role's private voice, autosaved as it is
 * edited. A failed save keeps the draft and offers a retry; the card's
 * autosave also submits the last edit when the role editor switches roles.
 */
export function RoleVoiceEditor({ roleId, client, voice, moodCatalog, disabled }: RoleVoiceEditorProps) {
  const host = usePluginHostServices();
  const preview = useSavedPreview(client, roleId, voice);
  const draft = voice.draft;
  if (!roleId) return <p className="m-0 text-body text-ink-muted">请先保存角色</p>;
  return <>
    <div className="flex justify-end"><host.ui.SettingsSavedStatus phase={voice.savePhase} /></div>
    {voice.loadError ? <host.ui.InlineError message={voice.loadError} actions={<button type="button" className={compactGhostButtonClass} onClick={voice.reload}>重新加载</button>} /> : null}
    {voice.saveError ? <host.ui.InlineError message={voice.saveError} actions={<button type="button" className={compactGhostButtonClass} onClick={voice.retry}>重试</button>} /> : null}
    {!draft && voice.loading ? <span className="text-body-sm text-ink-muted">正在读取声音设置…</span> : null}
    {draft ? <>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-2">文本语言<Select aria-label="文本语言" className={inputClass} disabled={disabled} value={draft.text_lang} options={voiceLanguages}
          onValueChange={(next) => { const language = voiceLanguage(next); if (language) voice.commit((current) => ({ ...current, text_lang: language })); }} /></label>
        <label className="grid gap-2">语速<input aria-label="语速" className={inputClass} disabled={disabled} type="number" min="0.5" max="2" step="0.1" defaultValue={draft.speed}
          onChange={(event) => { const speed = event.target.valueAsNumber; if (speed >= 0.5 && speed <= 2) voice.update((current) => ({ ...current, speed })); }} /></label>
      </div>
      <ReferenceList roleId={roleId} client={client} draft={draft} moodCatalog={moodCatalog} disabled={disabled}
        onUpdate={voice.update} onCommit={voice.commit} onPreview={preview.play} previewDisabled={disabled || preview.busy || preview.blockedReason !== "" || !preview.text.trim()} />
      <PreviewControls preview={preview} />
    </> : null}
  </>;
}
