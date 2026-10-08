import type { ChatSendRequest } from "../shared/types";
import { canSubmitChatMessage } from "./chatComposerState";

const emptyDraft: ChatSendRequest = { content: "", attachments: [], replyTarget: null };
const drafts = new Map<string, ChatSendRequest>();
const listeners = new Set<() => void>();

/** Desktop chats have one authoritative session per role, including while that session is loading. */
export function getChatDraftKey(activeRoleId: string): string | null {
  return activeRoleId ? `role:${activeRoleId}` : null;
}

/** Reads an in-memory draft; unchanged and absent drafts have stable snapshot identities. */
export function getChatDraft(key: string | null): ChatSendRequest {
  return key ? drafts.get(key) ?? emptyDraft : emptyDraft;
}

/** Subscribes across composer mounts; useSyncExternalStore skips unchanged session snapshots. */
export function subscribeChatDrafts(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** Updates only the explicitly captured source session, never a shared empty-session entry. */
export function updateChatDraft(key: string | null, update: (draft: ChatSendRequest) => ChatSendRequest): void {
  if (!key) return;
  const current = getChatDraft(key);
  const next = update(current);
  if (next === current) return;
  drafts.set(key, next);
  for (const listener of listeners) listener();
}

/** Submits a snapshot and restores a failed send only if its cleared draft is still untouched. */
export async function submitChatDraft(
  key: string | null,
  send: (request: ChatSendRequest) => Promise<boolean>,
): Promise<boolean> {
  const request = getChatDraft(key);
  if (!key || !canSubmitChatMessage(request.content, request.attachments)) return false;
  // A unique clear snapshot also distinguishes edits that were later erased.
  const cleared: ChatSendRequest = { content: "", attachments: [], replyTarget: null };
  updateChatDraft(key, () => cleared);
  let sent = false;
  try {
    sent = await send(request);
    return sent;
  } finally {
    if (!sent && getChatDraft(key) === cleared) updateChatDraft(key, () => request);
  }
}
