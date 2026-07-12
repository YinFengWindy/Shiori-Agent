import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import { cx, inputClass } from "../shared/styles";
import type { PromptTagEntry } from "./types";

export type PromptTagDraft = PromptTagEntry;

type PromptTagEntryEditorProps = {
  draft: PromptTagDraft;
  error: string;
  saving: boolean;
  bridgeReady: boolean;
  onChange: (draft: PromptTagDraft) => void;
  onSave: () => void;
};

function splitTags(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

/** Renders the editable fields for one prompt-tag catalog entry. */
export function PromptTagEntryEditor({
  draft,
  error,
  saving,
  bridgeReady,
  onChange,
  onSave,
}: PromptTagEntryEditorProps) {
  return (
    <div className="grid gap-2">
      <label className="grid gap-1 text-xs text-[#374151]"><span>ID / 名称</span><div className="grid grid-cols-2 gap-2"><input className={cx(inputClass, "border-[#D8DFE7] bg-white")} value={draft.id} onChange={(event) => onChange({ ...draft, id: event.target.value })} /><input className={cx(inputClass, "border-[#D8DFE7] bg-white")} value={draft.name} onChange={(event) => onChange({ ...draft, name: event.target.value })} /></div></label>
      <input className={cx(inputClass, "border-[#D8DFE7] bg-white")} placeholder="分类" value={draft.category} onChange={(event) => onChange({ ...draft, category: event.target.value })} />
      <input className={cx(inputClass, "border-[#D8DFE7] bg-white")} placeholder="匹配词（逗号分隔）" value={draft.match_terms.join(", ")} onChange={(event) => onChange({ ...draft, match_terms: splitTags(event.target.value) })} />
      <input className={cx(inputClass, "border-[#D8DFE7] bg-white")} placeholder="正向 tag（逗号分隔）" value={draft.positive_tags.join(", ")} onChange={(event) => onChange({ ...draft, positive_tags: splitTags(event.target.value) })} />
      <input className={cx(inputClass, "border-[#D8DFE7] bg-white")} placeholder="负向 tag（逗号分隔）" value={draft.negative_tags.join(", ")} onChange={(event) => onChange({ ...draft, negative_tags: splitTags(event.target.value) })} />
      <div className="flex items-center justify-between gap-2 text-xs text-[#374151]"><select className={cx(inputClass, "border-[#D8DFE7] bg-white")} value={draft.rating} onChange={(event) => onChange({ ...draft, rating: event.target.value as PromptTagEntry["rating"] })}><option value="general">general</option><option value="sensitive">sensitive</option><option value="adult">adult</option></select><label className="flex items-center gap-2"><span>启用</span><SettingsToggleCard checked={draft.enabled} ariaLabel="启用提示词条目" onChange={(checked) => onChange({ ...draft, enabled: checked })} /></label></div>
      {error ? <div className="text-xs text-[#A33]">{error}</div> : null}
      <button className="rounded-md bg-[#2F6FED] px-3 py-2 text-xs text-white disabled:opacity-50" type="button" disabled={!bridgeReady || saving} onClick={onSave}>{saving ? "保存中" : "保存条目"}</button>
    </div>
  );
}
