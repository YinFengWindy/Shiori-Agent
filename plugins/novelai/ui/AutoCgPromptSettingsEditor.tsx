import { compactGhostButtonClass, textareaClass, usePluginHostServices } from "@yinfengwindy/shiori-sdk";
import type { useAutoCgPromptSettings } from "./useAutoCgPromptSettings";

type AutoCgPromptSettingsEditorProps = {
  roleId: string | null;
  settings: ReturnType<typeof useAutoCgPromptSettings>;
  disabled: boolean;
};

/** The CG card's private prompt settings, with the shared save status and retry UI. */
export function AutoCgPromptSettingsEditor({ roleId, settings, disabled }: AutoCgPromptSettingsEditorProps) {
  const host = usePluginHostServices();
  if (!roleId) return <p className="m-0 text-body text-ink-muted">请先保存角色</p>;
  return <>
    <div className="flex justify-end"><host.ui.SettingsSavedStatus phase={settings.savePhase} /></div>
    {settings.loadError ? <host.ui.InlineError message={settings.loadError} actions={<button type="button" className={compactGhostButtonClass} onClick={settings.reload}>重新加载</button>} /> : null}
    {settings.saveError ? <host.ui.InlineError message={settings.saveError} actions={<button type="button" className={compactGhostButtonClass} onClick={settings.retry}>重试</button>} /> : null}
    {settings.loading ? <span className="text-body-sm text-ink-muted">正在读取补充要求…</span> : null}
    {settings.draft ? <label className="grid gap-2 text-body-sm text-ink">
      补充要求
      <textarea className={textareaClass} rows={6} disabled={disabled} value={settings.draft.prompt_instructions}
        onChange={(event) => { const prompt_instructions = event.target.value; settings.update(() => ({ prompt_instructions })); }} />
    </label> : null}
  </>;
}
