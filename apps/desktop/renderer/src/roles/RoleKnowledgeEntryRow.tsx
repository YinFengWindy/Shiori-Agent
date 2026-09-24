import { CaretDown } from "@phosphor-icons/react";
import { DeleteIcon } from "../shared/icons";
import { cx } from "../shared/styles";
import type { RoleKnowledgeEntry } from "../shared/types";
import { roleChipClass, roleFieldClass } from "./roleEditorStyles";
import { RoleKeywordInput } from "./RoleKeywordInput";
import { RoleKnowledgeEntryOptions } from "./RoleKnowledgeEntryOptions";
import { knowledgeEntryLabel } from "./roleKnowledgeEntries";

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
        className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 py-3 text-left focus:outline-none"
        type="button"
        aria-expanded={expanded}
        onClick={onToggle}
      >
        <span className="grid min-w-0 gap-1.5">
          <span className="truncate text-sm font-medium text-ink">{knowledgeEntryLabel(entry, index)}</span>
          <span className="flex flex-wrap gap-1.5">
            {keywords.length
              ? keywords.map((keyword) => <span className={roleChipClass} key={keyword}>{keyword}</span>)
              : null}
          </span>
        </span>
        <CaretDown className={cx("h-4 w-4 shrink-0 text-ink-faint transition-transform", expanded && "rotate-180")} weight="bold" />
      </button>
      {expanded ? (
        <div className="grid gap-3 pb-4">
          <label className="grid gap-1.5 text-xs text-ink-muted">
            <span>标题</span>
            <input
              className={roleFieldClass}
              value={entry.title ?? ""}
              placeholder="输入条目标题"
              onChange={(event) => onUpdate((current) => ({ ...current, title: event.target.value }))}
            />
          </label>
          <RoleKeywordInput label="关键词" keywords={keywords} onChange={(primary_keys) => onUpdate((current) => ({ ...current, primary_keys }))} />
          <RoleKeywordInput label="次关键词" keywords={entry.secondary_keys ?? []} onChange={(secondary_keys) => onUpdate((current) => ({ ...current, secondary_keys }))} />
          <RoleKnowledgeEntryOptions entry={entry} onUpdate={onUpdate} />
          <label className="grid gap-1.5 text-xs text-ink-muted">
            <span>内容</span>
            <textarea
              className={cx(roleFieldClass, "min-h-32 resize-none leading-6")}
              value={entry.content ?? ""}
              placeholder="输入会注入角色上下文的内容"
              onChange={(event) => onUpdate((current) => ({ ...current, content: event.target.value }))}
            />
          </label>
          <button
            className="inline-flex w-fit items-center gap-1.5 text-xs text-danger-text transition hover:text-danger-text focus:outline-none"
            type="button"
            onClick={onRemove}
            aria-label={`删除条目 ${index + 1}`}
            title="删除条目"
          >
            <DeleteIcon className="h-3.5 w-3.5 fill-current" />
            删除条目
          </button>
        </div>
      ) : null}
    </div>
  );
}
