import { CaretDown, Trash } from "@phosphor-icons/react";
import { compactButtonSizeClass, cx, dangerGhostButtonSurfaceClass } from "../shared/styles";
import type { RoleKnowledgeEntry } from "../shared/types";
import { roleChipClass, roleFieldClass, roleFieldLabelClass } from "./roleEditorStyles";
import { RoleKeywordInput } from "./RoleKeywordInput";
import { RoleKnowledgeEntryOptions } from "./RoleKnowledgeEntryOptions";
import { knowledgeEntryLabel } from "./roleKnowledgeEntries";
import { RoleTextareaField } from "./RoleTextareaField";

type RoleKnowledgeEntryRowProps = {
  entry: RoleKnowledgeEntry;
  index: number;
  expanded: boolean;
  onToggle: () => void;
  onUpdate: (update: (current: RoleKnowledgeEntry) => RoleKnowledgeEntry) => void;
  onRemove: () => void;
};

/** Renders one editable Lorebook entry with its keyword chips. */
export function RoleKnowledgeEntryRow({ entry, index, expanded, onToggle, onUpdate, onRemove }: RoleKnowledgeEntryRowProps) {
  const keywords = entry.primary_keys ?? entry.keywords ?? [];

  return (
    <div className="border-b border-line-soft last:border-b-0" data-testid={`knowledge-entry-${index}`}>
      <button
        className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-hover"
        type="button"
        aria-expanded={expanded}
        onClick={onToggle}
      >
        <span className="grid min-w-0 gap-1.5">
          <span className="truncate text-body font-medium text-ink">{knowledgeEntryLabel(entry, index)}</span>
          {keywords.length ? (
            <span className="flex flex-wrap gap-1.5">
              {keywords.map((keyword) => <span className={roleChipClass} key={keyword}>{keyword}</span>)}
            </span>
          ) : null}
        </span>
        <CaretDown className={cx("h-4 w-4 shrink-0 text-ink-muted transition-transform duration-quick", expanded && "rotate-180")} weight="bold" aria-hidden="true" />
      </button>
      {expanded ? (
        <div className="grid gap-4 px-4 pb-4">
          <label className={roleFieldLabelClass}>
            <span>标题</span>
            <input
              className={roleFieldClass}
              value={entry.title ?? ""}
              placeholder="输入条目标题"
              onChange={(event) => onUpdate((current) => ({ ...current, title: event.target.value }))}
            />
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <RoleKeywordInput label="关键词" keywords={keywords} onChange={(primary_keys) => onUpdate((current) => ({ ...current, primary_keys }))} />
            <RoleKeywordInput label="次关键词" keywords={entry.secondary_keys ?? []} onChange={(secondary_keys) => onUpdate((current) => ({ ...current, secondary_keys }))} />
          </div>
          <RoleTextareaField
            label="内容"
            value={entry.content ?? ""}
            minHeightClass="min-h-32"
            placeholder="输入会注入角色上下文的内容"
            onChange={(content) => onUpdate((current) => ({ ...current, content }))}
          />
          <RoleKnowledgeEntryOptions entry={entry} onUpdate={onUpdate} />
          <button
            className={cx(dangerGhostButtonSurfaceClass, compactButtonSizeClass, "w-fit")}
            type="button"
            onClick={onRemove}
            aria-label={`删除条目 ${index + 1}`}
          >
            <Trash className="h-4 w-4" aria-hidden="true" />
            删除条目
          </button>
        </div>
      ) : null}
    </div>
  );
}
