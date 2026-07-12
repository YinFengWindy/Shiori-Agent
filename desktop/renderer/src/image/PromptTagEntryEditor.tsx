import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import { toFileUrl } from "../shared/format";
import { UploadIcon } from "../shared/icons";
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
  isCreating: boolean;
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
  isCreating,
}: PromptTagEntryEditorProps) {
  async function pickReferenceImage(): Promise<void> {
    const [imagePath] = await window.miraDesktop.pickImages({ multiple: false });
    if (imagePath) onChange({ ...draft, image_path: imagePath });
  }

  const field = (label: string, value: string, onChange: (value: string) => void, placeholder: string) => <label className="grid gap-1.5 text-xs text-[#4B5563]"><span className="font-medium">{label}</span><textarea className={cx(inputClass, "min-h-[72px] resize-y border-[#D8DFE7] bg-white")} placeholder={placeholder} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
  return (
    <div className="flex h-full flex-col gap-5">
      <div><h2 className="text-base font-semibold text-[#263241]">{isCreating ? "新建条目" : draft.name || "编辑条目"}</h2></div>
      <div className="grid gap-4"><div className="grid gap-3 rounded-md border border-[#E5EAF0] p-4"><div className="text-xs font-semibold text-[#263241]">参考图片</div><button className="grid min-h-[180px] place-items-center overflow-hidden rounded-md border border-dashed border-[#D8DFE7] bg-[#F8FAFC] text-[#64748B] transition hover:bg-[#F1F5F9]" type="button" onClick={() => void pickReferenceImage()}>{draft.image_path ? <img className="max-h-[280px] w-full object-contain" src={toFileUrl(draft.image_path)} alt="参考图片" /> : <span className="grid place-items-center gap-2 text-xs"><UploadIcon className="h-6 w-6 fill-current" />选择参考图片</span>}</button></div><div className="grid gap-3 rounded-md border border-[#E5EAF0] p-4"><div className="text-xs font-semibold text-[#263241]">基础信息</div><div className="grid grid-cols-2 gap-3"><label className="grid gap-1.5 text-xs text-[#4B5563]"><span>ID</span><input className={cx(inputClass, "border-[#D8DFE7] bg-white")} value={draft.id} onChange={(event) => onChange({ ...draft, id: event.target.value })} /></label><label className="grid gap-1.5 text-xs text-[#4B5563]"><span>名称</span><input className={cx(inputClass, "border-[#D8DFE7] bg-white")} value={draft.name} onChange={(event) => onChange({ ...draft, name: event.target.value })} /></label></div><div className="grid grid-cols-2 gap-3"><label className="grid gap-1.5 text-xs text-[#4B5563]"><span>分类</span><input className={cx(inputClass, "border-[#D8DFE7] bg-white")} value={draft.category} onChange={(event) => onChange({ ...draft, category: event.target.value })} /></label><label className="grid gap-1.5 text-xs text-[#4B5563]"><span>使用限制</span><select className={cx(inputClass, "border-[#D8DFE7] bg-white")} value={draft.rating} onChange={(event) => onChange({ ...draft, rating: event.target.value as PromptTagEntry["rating"] })}><option value="general">通用</option><option value="sensitive">敏感</option><option value="adult">成人</option></select></label></div><label className="flex items-center justify-between text-xs text-[#4B5563]"><span>启用此条目</span><SettingsToggleCard checked={draft.enabled} ariaLabel="启用提示词条目" onChange={(checked) => onChange({ ...draft, enabled: checked })} /></label></div><div className="grid gap-3 rounded-md border border-[#E5EAF0] p-4"><div className="text-xs font-semibold text-[#263241]">匹配与 Tag</div>{field("匹配条件", draft.match_terms.join(", "), (value) => onChange({ ...draft, match_terms: splitTags(value) }), "输入触发词，用逗号分隔")}{field("正向 Tag", draft.positive_tags.join(", "), (value) => onChange({ ...draft, positive_tags: splitTags(value) }), "输入要自动加入的 tag，用逗号分隔")}{field("负向 Tag", draft.negative_tags.join(", "), (value) => onChange({ ...draft, negative_tags: splitTags(value) }), "可选，用逗号分隔")}</div></div>
      {error ? <div className="text-xs text-[#A33]">{error}</div> : null}
      <div className="mt-auto flex justify-end border-t border-[#E5EAF0] pt-4"><button className="rounded-md bg-[#2F6FED] px-4 py-2 text-xs font-medium text-white disabled:opacity-50" type="button" disabled={!bridgeReady || saving} onClick={onSave}>{saving ? "保存中" : "保存条目"}</button></div>
    </div>
  );
}
