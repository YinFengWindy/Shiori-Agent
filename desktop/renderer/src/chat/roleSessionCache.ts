import { createHotChatSession } from "./chatMessageWindow";
import type { SessionPayload } from "../shared/types";

export type RoleSessionCache = Record<string, SessionPayload>;

type ResolveImmediateRoleSessionOptions = {
  currentRoleId: string;
  nextRoleId: string;
  currentSession: SessionPayload | null;
  cachedSession: SessionPayload | null;
};

function normalizeRoleId(roleId: string): string {
  return roleId.trim();
}

/** Returns the most recent cached session for a role, if one exists. */
export function readRoleSessionCache(cache: RoleSessionCache, roleId: string) {
  const normalizedRoleId = normalizeRoleId(roleId);
  if (!normalizedRoleId) {
    return null;
  }
  return cache[normalizedRoleId] ?? null;
}

/** Resolves which session should be shown immediately while a role switch is still refreshing from the bridge. */
export function resolveImmediateRoleSession({
  currentRoleId,
  nextRoleId,
  currentSession,
  cachedSession,
}: ResolveImmediateRoleSessionOptions) {
  if (
    normalizeRoleId(currentRoleId) !== normalizeRoleId(nextRoleId)
    || !currentSession
  ) {
    return cachedSession ? createHotChatSession(cachedSession) : null;
  }
  return currentSession;
}

/** Writes the latest role session into cache while preserving the old object when nothing changed. */
export function writeRoleSessionCache(
  cache: RoleSessionCache,
  roleId: string,
  session: SessionPayload,
) {
  const normalizedRoleId = normalizeRoleId(roleId);
  if (!normalizedRoleId) {
    return cache;
  }
  if (cache[normalizedRoleId] === session) {
    return cache;
  }
  return {
    ...cache,
    [normalizedRoleId]: session,
  };
}

/** Removes a role session from cache after that role disappears from the desktop workspace. */
export function removeRoleSessionCache(cache: RoleSessionCache, roleId: string) {
  const normalizedRoleId = normalizeRoleId(roleId);
  if (!normalizedRoleId || !cache[normalizedRoleId]) {
    return cache;
  }
  const nextCache = { ...cache };
  delete nextCache[normalizedRoleId];
  return nextCache;
}

/** Prunes cached sessions whose role ids are no longer present in the current role list. */
export function retainRoleSessionCache(cache: RoleSessionCache, roleIds: readonly string[]) {
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
