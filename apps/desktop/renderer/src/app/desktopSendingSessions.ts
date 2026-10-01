type SendingSessionsMap = Record<string, string>;

/** Marks a chat session as sending while preserving the previous object when nothing changed. */
export function markSendingSessionState(
  current: SendingSessionsMap,
  sessionKey: string,
  roleId: string,
): SendingSessionsMap {
  if (!sessionKey || !roleId || current[sessionKey] === roleId) {
    return current;
  }
  return {
    ...current,
    [sessionKey]: roleId,
  };
}

/** Clears one in-flight chat session while preserving the previous object when it was already absent. */
export function clearSendingSessionState(
  current: SendingSessionsMap,
  sessionKey: string,
): SendingSessionsMap {
  if (!sessionKey || !current[sessionKey]) {
    return current;
  }
  const next = { ...current };
  delete next[sessionKey];
  return next;
}

/** Clears every in-flight chat session while preserving the previous object when already empty. */
export function clearAllSendingSessionsState(current: SendingSessionsMap): SendingSessionsMap {
  return Object.keys(current).length ? {} : current;
}

/** Returns whether the current session can send without being blocked by another role's in-flight turn. */
export function canSendSessionState(current: SendingSessionsMap, sessionKey: string): boolean {
  return Boolean(sessionKey) && !current[sessionKey];
}
