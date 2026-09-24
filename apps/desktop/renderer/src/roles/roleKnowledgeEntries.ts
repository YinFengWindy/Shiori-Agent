import type { RoleKnowledgeEntry } from "../shared/types";

/**
 * Whether removing this Lorebook entry would throw away anything the user
 * wrote. A freshly added, still-empty entry can be removed without asking;
 * one with a title, keywords or content goes through a confirmation.
 */
export function knowledgeEntryHasContent(entry: RoleKnowledgeEntry): boolean {
  return Boolean(
    entry.title?.trim()
    || entry.content?.trim()
    || (entry.primary_keys ?? entry.keywords ?? []).length
    || (entry.secondary_keys ?? []).length,
  );
}

/** Display name of an entry, matching the row header's fallback. */
export function knowledgeEntryLabel(entry: RoleKnowledgeEntry, index: number): string {
  return entry.title?.trim() || `条目 ${index + 1}`;
}
