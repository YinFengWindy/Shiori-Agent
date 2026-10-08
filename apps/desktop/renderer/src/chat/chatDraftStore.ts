import type { ChatSendRequest } from "../shared/types";
import { canSubmitChatMessage, normalizeChatAttachmentPaths } from "./chatComposerState";

const emptyDraft: ChatSendRequest = { content: "", attachments: [], replyTarget: null };
const drafts = new Map<string, { snapshot: ChatSendRequest; editRevision: number }>();
const listeners = new Set<() => void>();

/** Desktop chats have one authoritative session per role, including while that session is loading. */
export function getChatDraftKey(activeRoleId: string): string | null {
  return activeRoleId ? `role:${activeRoleId}` : null;
}

/** Reads an in-memory draft; unchanged and absent drafts have stable snapshot identities. */
export function getChatDraft(key: string | null): ChatSendRequest {
  return key ? drafts.get(key)?.snapshot ?? emptyDraft : emptyDraft;
}

/** Subscribes across composer mounts; useSyncExternalStore skips unchanged session snapshots. */
export function subscribeChatDrafts(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

function publishChatDraft(key: string, snapshot: ChatSendRequest, editRevision: number): void {
  drafts.set(key, { snapshot, editRevision });
  for (const listener of listeners) listener();
}

/** Records an explicit edit to the source session, preventing older sends from overwriting it. */
export function updateChatDraft(key: string | null, update: (draft: ChatSendRequest) => ChatSendRequest): void {
  if (!key) return;
  const current = getChatDraft(key);
  const next = update(current);
  if (next === current) return;
  publishChatDraft(key, next, (drafts.get(key)?.editRevision ?? 0) + 1);
}

/** Appends an async import result without treating its completion as a new user edit. */
export function appendImportedChatAttachments(key: string | null, paths: string[]): void {
  if (!key || !paths.length) return;
  const current = getChatDraft(key);
  const attachments = normalizeChatAttachmentPaths([...current.attachments, ...paths]);
  if (attachments.length === current.attachments.length) return;
  publishChatDraft(key, { ...current, attachments }, drafts.get(key)?.editRevision ?? 0);
}

/** Restores failed submissions unless explicitly edited, retaining any imports completed meanwhile. */
export async function submitChatDraft(
  key: string | null,
  send: (request: ChatSendRequest) => Promise<boolean>,
): Promise<boolean> {
  const request = getChatDraft(key);
  if (!key || !canSubmitChatMessage(request.content, request.attachments)) return false;
  // Submission advances ownership too, so an older send cannot restore over a newer one.
  const editRevision = (drafts.get(key)?.editRevision ?? 0) + 1;
  publishChatDraft(key, { content: "", attachments: [], replyTarget: null }, editRevision);
  let sent = false;
  try {
    sent = await send(request);
    return sent;
  } finally {
    if (!sent && drafts.get(key)?.editRevision === editRevision) {
      const imported = getChatDraft(key).attachments;
      publishChatDraft(key, imported.length ? {
        ...request,
        attachments: normalizeChatAttachmentPaths([...request.attachments, ...imported]),
      } : request, editRevision);
    }
  }
}
