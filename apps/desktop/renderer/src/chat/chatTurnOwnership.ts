/** Active renderer turn identities keyed by the session that owns them. */
export type ActiveChatTurns = Readonly<Record<string, string>>;

/** Returns whether a bridge event still belongs to the active renderer turn. */
export function isActiveChatTurn(
  activeTurns: ActiveChatTurns,
  sessionKey: string,
  turnId: string,
): boolean {
  return Boolean(sessionKey && turnId && activeTurns[sessionKey] === turnId);
}

/** Prevents an older cancellation request from surfacing after its turn has ended. */
export function shouldSurfaceChatCancellationFailure(
  activeTurns: ActiveChatTurns,
  sessionKey: string,
  turnId: string,
): boolean {
  return isActiveChatTurn(activeTurns, sessionKey, turnId);
}
