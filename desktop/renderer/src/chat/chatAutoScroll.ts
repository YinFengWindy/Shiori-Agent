export function shouldAutoScrollOnNewMessage({
  currentMessageCount,
  previousMessageCount,
  highlightedMessageKey,
  sending,
  wasAtBottom,
}: {
  currentMessageCount: number;
  previousMessageCount: number;
  highlightedMessageKey: string;
  sending: boolean;
  wasAtBottom: boolean;
}): boolean {
  if (highlightedMessageKey) {
    return false;
  }
  if (currentMessageCount <= previousMessageCount) {
    return false;
  }
  return sending || wasAtBottom;
}
