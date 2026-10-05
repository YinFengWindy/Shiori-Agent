import { CheckCircle, CaretRight } from "@phosphor-icons/react";
import { cx } from "@yinfengwindy/shiori-sdk";
import type { RoleCardExportFormat, RoleCardExportPreview } from "../../../src/bridge/roleCardExportContract";

const formats = [
  { value: "charx", label: "CHARX", detail: "资料＋素材" },
  { value: "png", label: "PNG", detail: "资料＋封面" },
  { value: "json", label: "JSON", detail: "仅资料" },
] as const;
const fields = [
  ["profile", "角色资料"], ["personality", "性格"],
  ["behavior_rules", "行为规则"], ["response_constraints", "回复约束"],
] as const;

/** Role identity, compact format choices, and individually expandable definitions. */
export function RoleCardExportDetails({ preview, format, busy, onSelectFormat }: {
  preview: RoleCardExportPreview | null;
  format: RoleCardExportFormat;
  busy: boolean;
  onSelectFormat: (format: RoleCardExportFormat) => void;
}) {
  const defined = fields.filter(([field]) => preview?.character[field]);
  return <>
    <div className="grid min-h-20 content-start gap-2">
      {preview ? <>
        <h3 className="break-words font-display text-headline font-semibold text-ink [overflow-wrap:anywhere]">{preview.name}</h3>
        {preview.character.nickname && preview.character.nickname !== preview.name ? <p className="break-words text-body text-ink-muted">{preview.character.nickname}</p> : null}
        {preview.description ? <p className="whitespace-pre-wrap break-words text-body leading-relaxed text-ink-secondary [overflow-wrap:anywhere]">{preview.description}</p> : null}
      </> : <div aria-hidden="true" className="grid gap-3 pt-1"><div className="h-7 w-2/3 rounded-md bg-surface-soft" /><div className="h-4 w-full rounded-md bg-surface-soft" /></div>}
    </div>
    <fieldset className="grid gap-2.5">
      <legend className="mb-2.5 text-body font-medium text-ink">导出格式</legend>
      <div className="grid grid-cols-3 gap-2">
        {formats.map((option) => <button key={option.value} type="button" aria-pressed={format === option.value} disabled={busy}
          onClick={() => onSelectFormat(option.value)}
          className={cx("grid min-w-0 gap-1.5 rounded-md border px-2 py-3 text-left transition-colors duration-quick disabled:opacity-50 sm:px-3",
            format === option.value ? "border-line-accent bg-accent-softer" : "border-line-soft bg-surface hover:bg-surface-hover")}>
          <span className="flex items-center justify-between gap-1 text-body font-semibold text-ink">{option.label}<CheckCircle weight="fill" aria-hidden="true" className={cx("h-4 w-4 shrink-0 text-accent-text", format !== option.value && "invisible")} /></span>
          <span className="whitespace-nowrap text-caption text-ink-muted">{option.detail}</span>
        </button>)}
      </div>
    </fieldset>
    <section aria-label="角色设定" className="grid gap-2">
      <h4 className="text-body font-medium text-ink">角色设定</h4>
      {defined.length ? <div className="divide-y divide-line-soft border-y border-line-soft">
        {defined.map(([field, label]) => <details key={`${preview?.export_id}-${field}`} open={field === "profile"} className="group">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 py-3 text-body text-ink-secondary [&::-webkit-details-marker]:hidden">
            <span>{label}</span><CaretRight className="h-3.5 w-3.5 shrink-0 group-open:rotate-90" aria-hidden="true" />
          </summary>
          <p className="whitespace-pre-wrap break-words pb-4 text-body leading-relaxed text-ink [overflow-wrap:anywhere]">{preview?.character[field]}</p>
        </details>)}
      </div> : <p className="py-2 text-body text-ink-muted">{preview ? "未填写设定" : "—"}</p>}
    </section>
  </>;
}
