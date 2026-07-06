import type { ChatReplyTarget } from "../shared/types";

/** One role's in-progress desktop chat composer state. */
export type ChatComposerStateSnapshot = {
  draft: string;
  attachments: string[];
  replyTarget: ChatReplyTarget | null;
};

/** Per-role cache for draft text, pending attachments, and reply targets. */
export type RoleComposerStateCache = Record<string, ChatComposerStateSnapshot>;

function normalizeRoleId(roleId: string): string {
  return roleId.trim();
}

/** Builds a normalized chat composer snapshot for one role. */
export function createChatComposerStateSnapshot(
  snapshot?: Partial<ChatComposerStateSnapshot>,
): ChatComposerStateSnapshot {
  return {
    draft: String(snapshot?.draft ?? ""),
    attachments: Array.isArray(snapshot?.attachments)
      ? snapshot.attachments.map((item) => item.trim()).filter(Boolean)
      : [],
    replyTarget: snapshot?.replyTarget ?? null,
  };
}

/** Returns the cached composer state for one role, if any. */
export function readRoleComposerStateCache(
  cache: RoleComposerStateCache,
  roleId: string,
): ChatComposerStateSnapshot | null {
  const normalizedRoleId = normalizeRoleId(roleId);
  if (!normalizedRoleId) {
    return null;
  }
  return cache[normalizedRoleId] ?? null;
}

/** Writes the latest composer state for a role while preserving the previous object when nothing changed. */
export function writeRoleComposerStateCache(
  cache: RoleComposerStateCache,
  roleId: string,
  snapshot: ChatComposerStateSnapshot,
): RoleComposerStateCache {
  const normalizedRoleId = normalizeRoleId(roleId);
  if (!normalizedRoleId) {
    return cache;
  }
  if (cache[normalizedRoleId] === snapshot) {
    return cache;
  }
  return {
    ...cache,
    [normalizedRoleId]: snapshot,
  };
}

/** Prunes cached composer state whose role ids are no longer present in the current role list. */
export function retainRoleComposerStateCache(
  cache: RoleComposerStateCache,
  roleIds: readonly string[],
): RoleComposerStateCache {
  const retainedRoleIds = new Set(roleIds.map(normalizeRoleId).filter(Boolean));
  let nextCache = cache;

  Object.keys(cache).forEach((roleId) => {
    if (retainedRoleIds.has(roleId)) {
      return;
    }
    if (nextCache === cache) {
      nextCache = { ...cache };
    }
    delete nextCache[roleId];
  });

  return nextCache;
}
