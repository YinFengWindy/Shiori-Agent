import { BookOpenText } from "@phosphor-icons/react";
import { PlusIcon } from "../shared/icons";
import { useState } from "react";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import type { RoleFormState, RoleKnowledgeBase, RoleKnowledgeEntry } from "../shared/types";
import {
  rolePanelGhostButtonClass,
  roleSectionTitleClass,
} from "./roleEditorStyles";
import { RoleKnowledgeEntryRow } from "./RoleKnowledgeEntryRow";
import { knowledgeEntryHasContent, knowledgeEntryLabel } from "./roleKnowledgeEntries";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";

type RoleKnowledgePanelProps = {
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Edits knowledge-base fields inside the shared role draft. */
export function RoleKnowledgePanel({ roleForm, onUpdate }: RoleKnowledgePanelProps) {
  const knowledge = roleForm.profile?.knowledge_base ?? {};
  const [expandedEntries, setExpandedEntries] = useState<ReadonlySet<string>>(new Set());
  const [pendingRemoveIndex, setPendingRemoveIndex] = useState<number | null>(null);
  const entries = knowledge.entries ?? [];
  const enabled = knowledge.enabled === true;

  function entryKey(entry: { id?: string }, index: number): string {
    return entry.id || `index-${index}`;
  }

  function updateKnowledge(update: (current: RoleKnowledgeBase) => RoleKnowledgeBase): void {
    onUpdate((current) => {
      const profile = current.profile ?? {};
      return {
        ...current,
        profile: {
          ...profile,
          knowledge_base: update(profile.knowledge_base ?? {}),
        },
      };
    });
  }

  function toggleEntry(index: number): void {
    setExpandedEntries((current) => {
      const next = new Set(current);
      const key = entryKey(entries[index] ?? {}, index);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function updateEntry(index: number, update: (current: RoleKnowledgeEntry) => RoleKnowledgeEntry): void {
    updateKnowledge((current) => ({
      ...current,
      entries: (current.entries ?? []).map((entry, entryIndex) => entryIndex === index ? update(entry) : entry),
    }));
  }

  function addEntry(): void {
    const id = crypto.randomUUID();
    updateKnowledge((current) => ({
      ...current,
      entries: [
        ...(current.entries ?? []),
        { id, content: "", primary_keys: [], secondary_keys: [], enabled: true, always_active: false, case_sensitive: false, priority: 0, insertion_order: current.entries?.length ?? 0 },
      ],
    }));
    setExpandedEntries((current) => new Set(current).add(id));
  }

  /** Removes an empty entry at once; one with written content is confirmed first. */
  function requestRemoveEntry(index: number): void {
    const entry = entries[index];
    if (entry && knowledgeEntryHasContent(entry)) {
      setPendingRemoveIndex(index);
      return;
    }
    removeEntry(index);
  }

  function removeEntry(index: number): void {
    const key = entryKey(entries[index] ?? {}, index);
    updateKnowledge((current) => ({
      ...current,
      entries: (current.entries ?? []).filter((_, entryIndex) => entryIndex !== index),
    }));
    setExpandedEntries((current) => {
      const next = new Set(current);
      next.delete(key);
      return next;
    });
  }

  return (
    <div className="grid gap-6" data-testid="role-knowledge-panel">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent-text" aria-hidden="true">
            <BookOpenText className="h-5 w-5" weight="duotone" />
          </span>
          <div>
            <h2 className={roleSectionTitleClass}>知识库</h2>
          </div>
        </div>
      </div>

      <div className="grid gap-4 border-y border-line-soft py-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-medium text-ink">启用知识库</h3>
          </div>
          <SettingsToggleCard checked={enabled} ariaLabel="启用知识库" onChange={(checked) => updateKnowledge((current) => ({ ...current, enabled: checked }))} />
        </div>
      </div>

      <div className="grid gap-1">
        <div className="flex items-center justify-between gap-4">
          <h3 className="text-sm font-medium text-ink">条目 · {entries.length}</h3>
          <button className={rolePanelGhostButtonClass} type="button" onClick={addEntry} aria-label="添加知识库条目" data-testid="add-knowledge-entry-button">
            <PlusIcon className="h-4 w-4 fill-current" />
            添加条目
          </button>
        </div>
        {entries.length ? (
          <div>
            {entries.map((entry, index) => (
              <RoleKnowledgeEntryRow
                entry={entry}
                index={index}
                expanded={expandedEntries.has(entryKey(entry, index))}
                onToggle={() => toggleEntry(index)}
                onUpdate={(update) => updateEntry(index, update)}
                onRemove={() => requestRemoveEntry(index)}
                key={entry.id ?? index}
              />
            ))}
          </div>
        ) : (
          <div className="mt-2 grid justify-items-center gap-2 border-y border-dashed border-line-soft py-8 text-center">
            <BookOpenText className="h-6 w-6 text-ink-faint" weight="duotone" aria-hidden="true" />
            <p className="text-xs text-ink-muted">当前没有知识库条目</p>
          </div>
        )}
      </div>
      <ConfirmDialog
        open={pendingRemoveIndex !== null && Boolean(entries[pendingRemoveIndex])}
        title="删除条目"
        description={pendingRemoveIndex !== null && entries[pendingRemoveIndex]
          ? `“${knowledgeEntryLabel(entries[pendingRemoveIndex], pendingRemoveIndex)}” 会从知识库中移除，保存角色后生效。`
          : ""}
        confirmLabel="删除"
        onClose={() => setPendingRemoveIndex(null)}
        onConfirm={() => {
          if (pendingRemoveIndex !== null) removeEntry(pendingRemoveIndex);
          setPendingRemoveIndex(null);
        }}
      />
    </div>
  );
}
