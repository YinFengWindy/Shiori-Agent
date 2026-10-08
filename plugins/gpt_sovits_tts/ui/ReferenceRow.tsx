import { ArrowsClockwiseIcon, CaretDownIcon, CaretRightIcon, PlayIcon, TrashIcon } from "@phosphor-icons/react";
import { compactGhostButtonClass, compactIconButtonClass, inputClass, Select, textareaClass } from "@yinfengwindy/shiori-sdk";
import type { VoiceLanguage, VoiceReference } from "../shared/contracts";
import { voiceLanguage, voiceLanguages } from "./languages";

type ReferenceRowProps = {
  title: string;
  /** Null for a mood still waiting for its audio: the row then only offers the import. */
  value: VoiceReference | null;
  expanded: boolean;
  disabled: boolean;
  /** This row's import is in flight. */
  importing: boolean;
  previewDisabled: boolean;
  onToggle(): void;
  /** Imports a new audio for the row, replacing an existing one. */
  onImport(): void;
  onPreview(): void;
  onDelete(): void;
  onTranscript(text: string): void;
  onLanguage(language: VoiceLanguage): void;
};

const rowClass = "grid rounded-md border border-line-soft";

/** One compact reference row: name, duration and transcript excerpt; a click expands its transcript and language. */
export function ReferenceRow({ title, value, expanded, disabled, importing, previewDisabled, onToggle, onImport, onPreview, onDelete, onTranscript, onLanguage }: ReferenceRowProps) {
  if (!value) {
    return <li className={rowClass} data-reference={title}>
      <div className="flex items-center gap-3 px-3 py-2">
        <span className="min-w-0 flex-1 truncate text-body text-ink-muted">{title}</span>
        <button type="button" className={compactGhostButtonClass} disabled={disabled} onClick={onImport}>{importing ? "导入中…" : "导入音频"}</button>
      </div>
    </li>;
  }
  const Caret = expanded ? CaretDownIcon : CaretRightIcon;
  return <li className={rowClass} data-reference={title}>
    <div className="flex items-center gap-1 py-1 pl-3 pr-1">
      <button type="button" className="flex min-w-0 flex-1 items-center gap-3 py-1 text-left" aria-expanded={expanded} onClick={onToggle}>
        <Caret className="h-3.5 w-3.5 shrink-0 text-ink-muted" weight="bold" aria-hidden="true" />
        <span className="shrink-0 text-body font-medium text-ink">{title}</span>
        <span className="shrink-0 text-caption text-ink-muted">{typeof value.duration === "number" ? `${value.duration.toFixed(1)} 秒` : "—"}</span>
        <span className="min-w-0 truncate text-caption text-ink-muted">{value.prompt_text}</span>
      </button>
      <button type="button" className={compactIconButtonClass} aria-label={`试听${title}`} disabled={previewDisabled} onClick={onPreview}><PlayIcon className="h-4 w-4" weight="bold" aria-hidden="true" /></button>
      <button type="button" className={compactIconButtonClass} aria-label={`更换${title}音频`} aria-busy={importing} disabled={disabled} onClick={onImport}><ArrowsClockwiseIcon className="h-4 w-4" weight="bold" aria-hidden="true" /></button>
      <button type="button" className={compactIconButtonClass} aria-label={`删除${title}`} disabled={disabled} onClick={onDelete}><TrashIcon className="h-4 w-4" weight="bold" aria-hidden="true" /></button>
    </div>
    {expanded ? <div className="grid gap-3 border-t border-line-soft p-3">
      <label className="grid gap-2">参考转写<textarea aria-label={`${title}参考转写`} className={textareaClass} rows={2} disabled={disabled} value={value.prompt_text} onChange={(event) => onTranscript(event.target.value)} /></label>
      <label className="grid gap-2">参考语言<Select aria-label={`${title}参考语言`} className={inputClass} disabled={disabled} value={value.prompt_lang} options={voiceLanguages} onValueChange={(next) => { const language = voiceLanguage(next); if (language) onLanguage(language); }} /></label>
    </div> : null}
  </li>;
}
