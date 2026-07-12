import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import { toFileUrl } from "../shared/format";
import { BackIcon, ResetIcon, SaveIcon, UploadIcon } from "../shared/icons";
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
  onBack: () => void;
  onReset: () => void;
  isCreating: boolean;
  dirty: boolean;
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
  onBack,
  onReset,
  isCreating,
  dirty,
}: PromptTagEntryEditorProps) {
  async function pickReferenceImage(): Promise<void> {
    const [imagePath] = await window.miraDesktop.pickImages({ multiple: false });
    if (imagePath) onChange({ ...draft, image_path: imagePath });
  }

  const field = (label: string, value: string, onChange: (value: string) => void, placeholder: string) => <label className="grid gap-1.5 text-xs text-[#4B5563]"><span className="font-medium">{label}</span><textarea className={cx(inputClass, "min-h-[72px] resize-y border-[#D8DFE7] bg-white")} placeholder={placeholder} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
  return (
    <div className="flex h-full flex-col gap-5">
      <div className="flex items-start justify-between gap-4">
        <button className="grid h-10 w-10 place-items-center rounded-full border border-black/8 bg-white/90 shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 hover:border-black/14 hover:bg-[#F5F7FA]" type="button" aria-label="返回提示词列表" onClick={onBack}><BackIcon className="h-5 w-5 fill-current" /></button>
        <div className="flex items-center gap-2.5">
          <button className="grid h-10 w-10 place-items-center rounded-full border border-black/8 bg-white/90 text-[#747474] shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 hover:border-black/14 hover:bg-[#F5F7FA] disabled:opacity-40" type="button" aria-label="重置提示词" disabled={saving || !dirty} onClick={onReset}><ResetIcon className="h-[18px] w-[18px] fill-current" /></button>
          <button className="grid h-10 w-10 place-items-center rounded-full border border-transparent bg-white text-[#1f1f1f] shadow-[0_8px_24px_rgba(15,23,42,0.08)] transition duration-200 hover:-translate-y-0.5 hover:bg-[#F5F7FA] disabled:opacity-40" type="button" aria-label={saving ? "正在保存提示词" : "保存提示词"} disabled={!bridgeReady || saving || !dirty} onClick={onSave}><SaveIcon className="h-5 w-5 fill-current" /></button>
        </div>
      </div>
      <div className="grid gap-4"><div className="grid gap-3 rounded-md border border-[#E5EAF0] p-4"><div className="text-xs font-semibold text-[#263241]">参考图片</div><button className="grid min-h-[180px] place-items-center overflow-hidden rounded-md border border-dashed border-[#D8DFE7] bg-[#F8FAFC] text-[#64748B] transition hover:bg-[#F1F5F9]" type="button" onClick={() => void pickReferenceImage()}>{draft.image_path ? <img className="max-h-[280px] w-full object-contain" src={toFileUrl(draft.image_path)} alt="参考图片" /> : <span className="grid place-items-center gap-2 text-xs"><UploadIcon className="h-6 w-6 fill-current" />选择参考图片</span>}</button></div><div className="grid gap-3 rounded-md border border-[#E5EAF0] p-4"><div className="text-xs font-semibold text-[#263241]">基础信息</div><div className="grid grid-cols-2 gap-3"><label className="grid gap-1.5 text-xs text-[#4B5563]"><span>ID</span><input className={cx(inputClass, "border-[#D8DFE7] bg-white")} value={draft.id} onChange={(event) => onChange({ ...draft, id: event.target.value })} /></label><label className="grid gap-1.5 text-xs text-[#4B5563]"><span>名称</span><input className={cx(inputClass, "border-[#D8DFE7] bg-white")} value={draft.name} onChange={(event) => onChange({ ...draft, name: event.target.value })} /></label></div><div className="grid grid-cols-2 gap-3"><label className="grid gap-1.5 text-xs text-[#4B5563]"><span>分类</span><input className={cx(inputClass, "border-[#D8DFE7] bg-white")} value={draft.category} onChange={(event) => onChange({ ...draft, category: event.target.value })} /></label><label className="grid gap-1.5 text-xs text-[#4B5563]"><span>使用限制</span><select className={cx(inputClass, "border-[#D8DFE7] bg-white")} value={draft.rating} onChange={(event) => onChange({ ...draft, rating: event.target.value as PromptTagEntry["rating"] })}><option value="general">通用</option><option value="sensitive">敏感</option><option value="adult">成人</option></select></label></div><label className="flex items-center justify-between text-xs text-[#4B5563]"><span>启用此条目</span><SettingsToggleCard checked={draft.enabled} ariaLabel="启用提示词条目" onChange={(checked) => onChange({ ...draft, enabled: checked })} /></label></div><div className="grid gap-3 rounded-md border border-[#E5EAF0] p-4"><div className="text-xs font-semibold text-[#263241]">匹配与 Tag</div>{field("匹配条件", draft.match_terms.join(", "), (value) => onChange({ ...draft, match_terms: splitTags(value) }), "输入触发词，用逗号分隔")}{field("正向 Tag", draft.positive_tags.join(", "), (value) => onChange({ ...draft, positive_tags: splitTags(value) }), "输入要自动加入的 tag，用逗号分隔")}{field("负向 Tag", draft.negative_tags.join(", "), (value) => onChange({ ...draft, negative_tags: splitTags(value) }), "可选，用逗号分隔")}</div></div>
      {error ? <div className="text-xs text-[#A33]">{error}</div> : null}
    </div>
  );
}
