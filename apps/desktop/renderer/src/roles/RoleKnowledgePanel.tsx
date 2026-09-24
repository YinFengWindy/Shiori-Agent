import { BookOpenText, Plus } from "@phosphor-icons/react";
import { cardClass, cx } from "../shared/styles";
import { useState } from "react";
import { SettingsToggleCard } from "../settings/SettingsToggleCard";
import type { RoleFormState, RoleKnowledgeBase, RoleKnowledgeEntry } from "../shared/types";
import { rolePanelGhostButtonClass } from "./roleEditorStyles";
import { RoleEditorSection } from "./RoleEditorSection";
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
    <div className="grid gap-7" data-testid="role-knowledge-panel">
      <RoleEditorSection
        title="知识库"
        action={<SettingsToggleCard checked={enabled} ariaLabel="启用知识库" onChange={(checked) => updateKnowledge((current) => ({ ...current, enabled: checked }))} />}
      >
        <div className="grid gap-3">
          <div className="flex items-center justify-between gap-4">
            <h3 className="m-0 text-body-sm font-medium text-ink-secondary">条目 · {entries.length}</h3>
            <button className={rolePanelGhostButtonClass} type="button" onClick={addEntry} aria-label="添加知识库条目" data-testid="add-knowledge-entry-button">
              <Plus className="h-4 w-4" weight="bold" aria-hidden="true" />
              添加条目
            </button>
          </div>
          {entries.length ? (
            <div className={cx(cardClass, "overflow-hidden")}>
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
            <div className="grid justify-items-center gap-2 rounded-lg border border-dashed border-line bg-surface-soft py-8 text-center">
              <BookOpenText className="h-6 w-6 text-ink-faint" weight="duotone" aria-hidden="true" />
              <p className="m-0 text-caption text-ink-muted">当前没有知识库条目</p>
            </div>
          )}
        </div>
      </RoleEditorSection>
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
