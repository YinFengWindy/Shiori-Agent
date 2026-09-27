/** File name of one role-owned Markdown memory document. */
export type RoleMemoryDocumentName = "SELF.md" | "MEMORY.md" | "HISTORY.md" | "RECENT_CONTEXT.md" | "PENDING.md";

/**
 * Read-only state of one memory document; mirrors `RoleMemoryService.read_documents`,
 * where an unreadable file always carries its error message.
 */
export type RoleMemoryDocument =
  | { name: RoleMemoryDocumentName; status: "ready" | "empty" | "missing"; content: string }
  | { name: RoleMemoryDocumentName; status: "error"; content: string; error: string };

/** `roles.memory.documents` response scoped to one persisted role. */
export type RoleMemoryDocumentsPayload = {
  role_id: string;
  documents: RoleMemoryDocument[];
};

/** A memory page tab: the semantic timeline or one Markdown document. */
export type MemoryTab = "timeline" | RoleMemoryDocumentName;

/** Document tabs in navigation order, after the timeline. */
export const memoryDocumentTabs: ReadonlyArray<{ name: RoleMemoryDocumentName; label: string }> = [
  { name: "SELF.md", label: "自我" },
  { name: "MEMORY.md", label: "长期" },
  { name: "HISTORY.md", label: "经历" },
  { name: "RECENT_CONTEXT.md", label: "近期" },
  { name: "PENDING.md", label: "待整理" },
];
