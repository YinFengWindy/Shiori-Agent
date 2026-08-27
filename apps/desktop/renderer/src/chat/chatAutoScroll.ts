export function shouldAutoScrollOnNewMessage({
  currentMessageCount,
  previousMessageCount,
  lastMessageContent,
  previousLastMessageContent,
  highlightedMessageKey,
  sending,
  wasAtBottom,
}: {
  currentMessageCount: number;
  previousMessageCount: number;
  lastMessageContent: string;
  previousLastMessageContent: string;
  highlightedMessageKey: string;
  sending: boolean;
  wasAtBottom: boolean;
}): boolean {
  if (highlightedMessageKey) {
    return false;
  }
  const appendedMessage = currentMessageCount > previousMessageCount;
  const expandedLastMessage =
    currentMessageCount === previousMessageCount
    && lastMessageContent !== previousLastMessageContent;
  if (!appendedMessage && !expandedLastMessage) {
    return false;
  }
  return sending || wasAtBottom;
}
