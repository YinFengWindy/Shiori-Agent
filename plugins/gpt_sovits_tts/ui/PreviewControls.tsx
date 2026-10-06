import { useState } from "react";
import { ghostButtonClass, inputClass, textareaClass, Select, usePluginHostServices, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { usePreview } from "./usePreview";

/** Synthesizes saved role settings through the public service and delegates playback to its background. */
export function PreviewControls({ client, roleId, moods, disabled }: { client: PluginRpcClient; roleId: string | null; moods: readonly string[]; disabled: boolean }) {
  const host = usePluginHostServices();
  const preview = usePreview(client, roleId, host.feedback);
  const [text, setText] = useState("你好，今天过得怎么样？");
  const [mood, setMood] = useState("");
  const selectedMood = moods.includes(mood) ? mood : "";
  return <section className="grid gap-3 border-t border-line-soft pt-4">
    <h3 className="text-body font-medium text-ink">试听</h3>
    <textarea aria-label="试听文本" className={textareaClass} rows={2} value={text} onChange={(event) => setText(event.target.value)} />
    <Select aria-label="试听情绪" className={inputClass} value={selectedMood} options={[{ value: "", label: "默认参考" }, ...moods.map((value) => ({ value, label: value }))]} onValueChange={setMood} />
    <div className="flex items-center gap-2">
      <button className={ghostButtonClass} disabled={disabled || preview.busy || !text.trim()} onClick={() => void preview.start(text, selectedMood)}>试听</button>
      <button className={ghostButtonClass} disabled={!preview.busy} onClick={() => void preview.stop()}>停止</button>
      {preview.busy ? <span className="text-caption text-ink-muted" role="status">{preview.state.phase === "playing" ? "播放中" : "生成中…"}</span> : null}
    </div>
    {preview.state.error ? <host.ui.InlineError message={preview.state.error} /> : null}
  </section>;
}
