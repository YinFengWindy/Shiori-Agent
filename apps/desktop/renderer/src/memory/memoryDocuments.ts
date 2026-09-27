/** Read-only state of one role-owned Markdown memory document. */
export type RoleMemoryDocument = {
  name: "SELF.md" | "MEMORY.md" | "HISTORY.md" | "RECENT_CONTEXT.md" | "PENDING.md";
  status: "ready" | "empty" | "missing" | "error";
  content: string;
  error?: string;
};

/** `roles.memory.documents` response scoped to one persisted role. */
export type RoleMemoryDocumentsPayload = {
  role_id: string;
  documents: RoleMemoryDocument[];
};

/** A memory page tab: the semantic timeline or one Markdown document. */
export type MemoryTab = "timeline" | RoleMemoryDocument["name"];

/** Document tabs in navigation order, after the timeline. */
export const memoryDocumentTabs: ReadonlyArray<{ name: RoleMemoryDocument["name"]; label: string }> = [
  { name: "SELF.md", label: "自我" },
  { name: "MEMORY.md", label: "长期" },
  { name: "HISTORY.md", label: "经历" },
  { name: "RECENT_CONTEXT.md", label: "近期" },
  { name: "PENDING.md", label: "待整理" },
];
