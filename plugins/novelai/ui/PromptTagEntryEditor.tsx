import { useEffect, useState, type ReactNode } from "react";
import { ArrowLeft, ImageSquare } from "@phosphor-icons/react";
import { usePluginHostServices } from "../../../apps/desktop/renderer/src/plugins/PluginHostServicesProvider";
import { SettingsToggleCard } from "../../../apps/desktop/renderer/src/settings/SettingsToggleCard";
import { toFileUrl } from "../../../apps/desktop/renderer/src/shared/format";
import {
  cardClass,
  compactButtonSizeClass,
  cx,
  ghostButtonSurfaceClass,
  iconButtonClass,
  inputClass,
  pressableClass,
  primaryButtonSurfaceClass,
  textareaClass,
} from "../../../apps/desktop/renderer/src/shared/styles";
import { Select } from "../../../apps/desktop/renderer/src/shared/ui/Select";
import type { PromptTagEntry } from "./types";

type PromptTagEntryEditorProps = {
  draft: PromptTagEntry;
  creating: boolean;
  error: string;
  saving: boolean;
  bridgeReady: boolean;
  dirty: boolean;
  onChange: (draft: PromptTagEntry) => void;
  onSave: () => void;
  onBack: () => void;
  onReset: () => void;
};

const ratingOptions = [
  { value: "general", label: "全年龄" },
  { value: "sensitive", label: "敏感" },
  { value: "adult", label: "成人（仅 NSFW 模式）", triggerLabel: "成人" },
];

function splitTags(value: string): string[] {
  return value.split(/[,，]/).map((item) => item.trim()).filter(Boolean);
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="grid min-w-0 gap-1.5">
      <span className="flex items-baseline gap-2 text-caption font-medium text-ink-secondary">
        {label}
        {hint ? <span className="font-normal text-ink-muted">{hint}</span> : null}
      </span>
      {children}
    </label>
  );
}

/**
 * A comma-separated list edited as free text: the text is kept locally so a
 * trailing comma or space survives typing, and only resyncs when the list
 * changes from outside (another entry opened, 还原).
 */
function TagListField({ label, hint, value, placeholder, onChange }: { label: string; hint?: string; value: string[]; placeholder: string; onChange: (value: string[]) => void }) {
  const joined = value.join(", ");
  const [text, setText] = useState(joined);
  useEffect(() => {
    setText((current) => (splitTags(current).join(", ") === joined ? current : joined));
  }, [joined]);
  return (
    <Field label={label} hint={hint}>
      <textarea
        className={cx(textareaClass, "min-h-20")}
        placeholder={placeholder}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          onChange(splitTags(event.target.value));
        }}
      />
    </Field>
  );
}

/** Edits one prompt-tag entry: reference image beside its identity, then its match terms and tags. */
export function PromptTagEntryEditor({ draft, creating, error, saving, bridgeReady, dirty, onChange, onSave, onBack, onReset }: PromptTagEntryEditorProps) {
  const host = usePluginHostServices();
  async function pickReferenceImage(): Promise<void> {
    const [imagePath] = await host.pickImages({ multiple: false });
    if (imagePath) onChange({ ...draft, image_path: imagePath });
  }

  return (
    <div className="grid gap-5" data-testid="prompt-tag-editor">
      <header className="flex items-center gap-3">
        <button className={iconButtonClass} type="button" aria-label="返回提示词库" onClick={onBack}>
          <ArrowLeft className="h-[18px] w-[18px]" aria-hidden="true" />
        </button>
        <h2 className="m-0 min-w-0 flex-1 truncate font-display text-headline text-ink">
          {creating ? "新建提示词" : (draft.name || "未命名")}
        </h2>
        <button className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} type="button" disabled={saving || !dirty} onClick={onReset}>
          还原
        </button>
        <button className={cx(primaryButtonSurfaceClass, compactButtonSizeClass)} type="button" disabled={!bridgeReady || saving || !dirty} onClick={onSave}>
          {saving ? "保存中…" : "保存"}
        </button>
      </header>
      {error ? <p className="m-0 rounded-md bg-danger-soft px-3 py-2 text-body-sm text-danger-text" role="alert">{error}</p> : null}

      <div className="grid grid-cols-[minmax(180px,260px)_minmax(0,1fr)] gap-5">
        <section className={cx(cardClass, "grid content-start gap-3 self-start p-4")}>
          <span className="text-body-sm font-semibold text-ink">参考图</span>
          <button
            className={cx(
              pressableClass,
              "grid aspect-[4/5] w-full place-items-center overflow-hidden rounded-md border border-dashed border-line bg-surface-soft text-ink-muted hover:border-line-accent hover:bg-accent-softer hover:text-accent-text",
            )}
            type="button"
            aria-label={draft.image_path ? "更换参考图" : "选择参考图"}
            onClick={() => void pickReferenceImage()}
          >
            {draft.image_path ? (
              <img className="h-full w-full object-cover" src={toFileUrl(draft.image_path)} alt="参考图" />
            ) : (
              <span className="grid justify-items-center gap-2 text-body-sm">
                <ImageSquare className="h-7 w-7" aria-hidden="true" />
                选择参考图
              </span>
            )}
          </button>
        </section>

        <div className="grid content-start gap-5">
          <section className={cx(cardClass, "grid gap-4 p-4")}>
            <span className="text-body-sm font-semibold text-ink">基本信息</span>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="名称">
                <input className={inputClass} value={draft.name} onChange={(event) => onChange({ ...draft, name: event.target.value })} />
              </Field>
              <Field label="标识" hint="ID">
                <input className={cx(inputClass, "font-mono")} value={draft.id} disabled={!creating} onChange={(event) => onChange({ ...draft, id: event.target.value })} />
              </Field>
              <Field label="分类">
                <input className={inputClass} value={draft.category} onChange={(event) => onChange({ ...draft, category: event.target.value })} />
              </Field>
              <Field label="分级">
                <Select aria-label="分级" value={draft.rating} options={ratingOptions} onValueChange={(value) => onChange({ ...draft, rating: value as PromptTagEntry["rating"] })} />
              </Field>
            </div>
            <div className="flex items-center justify-between gap-3 text-body-sm text-ink-secondary">
              <span>启用</span>
              <SettingsToggleCard checked={draft.enabled} ariaLabel="启用提示词" onChange={(enabled) => onChange({ ...draft, enabled })} />
            </div>
          </section>

          <section className={cx(cardClass, "grid gap-4 p-4")}>
            <span className="text-body-sm font-semibold text-ink">匹配与标签</span>
            <TagListField label="匹配词" hint="逗号分隔" value={draft.match_terms} placeholder="窗边, 靠窗" onChange={(match_terms) => onChange({ ...draft, match_terms })} />
            <TagListField label="正向标签" hint="逗号分隔" value={draft.positive_tags} placeholder="window, sitting" onChange={(positive_tags) => onChange({ ...draft, positive_tags })} />
            <TagListField label="负向标签" hint="可选" value={draft.negative_tags} placeholder="lowres" onChange={(negative_tags) => onChange({ ...draft, negative_tags })} />
          </section>
        </div>
      </div>
    </div>
  );
}
