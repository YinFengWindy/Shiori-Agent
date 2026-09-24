/** Resolves the session key for the chat currently shown in the desktop surface. */
export function resolveVisibleChatSessionKey(activeRoleId: string, activeSessionKey: string): string {
  const normalizedRoleId = activeRoleId.trim();
  if (normalizedRoleId) {
    return `role:${normalizedRoleId}`;
  }
  return activeSessionKey;
}

/**
 * Resolves the visible chat header title. It stays the role's name while a
 * reply streams: the typing state is a secondary line in the header, so the
 * title never flickers away from who the user is talking to.
 */
export function resolveChatHeaderTitle(activeRoleName: string | null) {
  return activeRoleName || "选择一个角色";
}
