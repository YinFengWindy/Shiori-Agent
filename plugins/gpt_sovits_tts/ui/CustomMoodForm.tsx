import { useState } from "react";
import { compactGhostButtonClass, inputClass, usePluginHostServices } from "@yinfengwindy/shiori-sdk";
import { emotionNameError } from "./emotionReferenceState";

/**
 * A mood outside the role catalog: a valid name goes straight to the audio
 * import, and only a successful import adds it. `onImport` resolves whether it did.
 */
export function CustomMoodForm({ existing, disabled, importing, onImport }: {
  existing: readonly string[]; disabled: boolean; importing: boolean; onImport(name: string): Promise<boolean>;
}) {
  const host = usePluginHostServices();
  const [name, setName] = useState("");
  const [error, setError] = useState("");

  async function submit() {
    const failure = emotionNameError(name, existing);
    setError(failure);
    if (failure) return;
    if (await onImport(name.trim())) setName("");
  }

  return <div className="grid gap-2">
    <div className="flex items-center gap-2">
      <input aria-label="情绪名称" placeholder="情绪名称" className={inputClass} disabled={disabled} value={name}
        onChange={(event) => setName(event.target.value)}
        onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void submit(); } }} />
      <button type="button" className={compactGhostButtonClass} disabled={disabled} onClick={() => void submit()}>{importing ? "导入中…" : "添加情绪"}</button>
    </div>
    {error ? <host.ui.InlineError message={error} /> : null}
  </div>;
}
