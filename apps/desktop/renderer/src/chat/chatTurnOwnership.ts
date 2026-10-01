/** Recorded renderer turn identities keyed by the session that owns them. */
export type ChatTurnIds = Readonly<Record<string, string>>;

/** Checks whether a session still records the expected turn identity. */
export function matchesChatTurn(
  turnIds: ChatTurnIds,
  sessionKey: string,
  turnId: string,
): boolean {
  return Boolean(sessionKey && turnId && turnIds[sessionKey] === turnId);
}
