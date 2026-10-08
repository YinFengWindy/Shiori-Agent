import { compactGhostButtonClass, textareaClass, usePluginHostServices } from "@yinfengwindy/shiori-sdk";
import type { useSavedPreview } from "./useSavedPreview";

/** The preview text and the running preview's stop, status and errors; each reference row starts its own preview. */
export function PreviewControls({ preview }: { preview: ReturnType<typeof useSavedPreview> }) {
  const host = usePluginHostServices();
  return <section className="grid gap-3 border-t border-line-soft pt-4" aria-label="试听">
    <textarea aria-label="试听文本" className={textareaClass} rows={2} value={preview.text} onChange={(event) => preview.setText(event.target.value)} />
    <div className="flex items-center gap-2">
      <button type="button" className={compactGhostButtonClass} disabled={!preview.busy} onClick={preview.stop}>停止</button>
      {preview.busy ? <span className="text-caption text-ink-muted" role="status">{preview.state.phase === "playing" ? "播放中" : "生成中…"}</span> : null}
      {preview.blockedReason ? <span className="text-caption text-ink-muted">{preview.blockedReason}</span> : null}
    </div>
    {preview.state.error ? <host.ui.InlineError message={preview.state.error} /> : null}
  </section>;
}
