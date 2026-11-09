import { useState } from "react";
import { compactGhostButtonClass, inputClass, Select, usePluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import type { useRoleVoice } from "./useRoleVoice";
import { usePreview } from "./usePreview";
import { textLanguage, textLanguages } from "./languages";

type Props = { client: PluginRpcClient; roleId: string | null; active: boolean; voice: ReturnType<typeof useRoleVoice>; disabled: boolean };

/** The role details dialog edits the selected role's voice and provides standalone preview. */
export function RoleVoiceEditor({ client, roleId, active, voice, disabled }: Props) {
  const host = usePluginHostServices();
  // Capability dialogs keep their content mounted while closed.
  const preview = usePreview(client, active ? roleId : null, host.feedback);
  const [text, setText] = useState("你好，今天过得怎么样？");
  const draft = voice.draft;
  if (!roleId) return <p className="m-0 text-body text-ink-muted">请先保存角色</p>;
  return <>
    <host.ui.SettingsSavedStatus phase={voice.savePhase} />
    {voice.loadError ? <host.ui.InlineError message={voice.loadError} actions={<button type="button" className={compactGhostButtonClass} onClick={voice.reload}>重新加载</button>} /> : null}
    {voice.saveError ? <host.ui.InlineError message={voice.saveError} actions={<button type="button" className={compactGhostButtonClass} onClick={voice.retry}>重试</button>} /> : null}
    {draft ? <div className="grid gap-3">
      <label className="grid gap-2">声音 ID<input aria-label="Fish Audio 声音 ID" className={inputClass} value={draft.reference_id} disabled={disabled} maxLength={256}
        onChange={(event) => { const reference_id = event.target.value; voice.update((current) => ({ ...current, reference_id })); }} onBlur={() => voice.commit()} /></label>
      <label className="grid gap-2" title="用于数字、日期、单位等文本规范化，不翻译文本或改变音色与口音">文本语言<Select aria-label="Fish Audio 文本语言" className={inputClass} value={draft.language} options={textLanguages} disabled={disabled}
        onValueChange={(value) => { const language = textLanguage(value); if (language) voice.commit((current) => ({ ...current, language })); }} /></label>
      <label className="grid gap-2">语速 · {draft.speed.toFixed(1)}<input aria-label="Fish Audio 语速" type="range" min="0.5" max="2" step="0.1" value={draft.speed} disabled={disabled}
        onChange={(event) => { const speed = Number(event.target.value); voice.update((current) => ({ ...current, speed })); }} /></label>
      <label className="grid gap-2">试听文本<textarea aria-label="Fish Audio 试听文本" className={inputClass} rows={3} maxLength={10000} value={text} onChange={(event) => setText(event.target.value)} /></label>
      <div className="flex justify-end gap-2">
        <button type="button" className={compactGhostButtonClass} disabled={disabled || preview.busy || voice.savePhase !== "idle" || !draft.reference_id.trim() || !text.trim()} onClick={() => void preview.start(text)}>试听</button>
        <button type="button" className={compactGhostButtonClass} disabled={!preview.busy} onClick={() => void preview.stop()}>停止试听</button>
      </div>
      {preview.busy ? <span role="status" className="text-body-sm text-ink-muted">{preview.state.phase === "generating" ? "生成中…" : "播放中…"}</span> : null}
      {preview.state.error ? <host.ui.InlineError message={preview.state.error} /> : null}
    </div> : null}
  </>;
}
