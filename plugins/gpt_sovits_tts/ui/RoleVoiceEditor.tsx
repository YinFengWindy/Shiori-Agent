import { compactGhostButtonClass, inputClass, Select, usePluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { voiceLanguage, voiceLanguages } from "./languages";
import { PreviewControls } from "./PreviewControls";
import { ReferenceList } from "./ReferenceList";
import { SpeedField } from "./SpeedField";
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
 * edited. A failed save keeps the draft and offers a retry; the card submits
 * the last edit when the dialog closes or the role editor switches roles.
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
        <SpeedField value={draft.speed} disabled={disabled} onChange={(speed) => voice.update((current) => ({ ...current, speed }))} />
      </div>
      <ReferenceList roleId={roleId} client={client} voice={{ ...voice, draft }} moodCatalog={moodCatalog} disabled={disabled}
        onPreview={preview.play} previewDisabled={disabled || preview.busy || preview.blockedReason !== "" || !preview.text.trim()} />
      <PreviewControls preview={preview} />
    </> : null}
  </>;
}
