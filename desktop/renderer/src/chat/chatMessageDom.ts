/** Finds one rendered chat message element by its message key. */
export function findChatMessageElement(messageKey: string): HTMLElement | null {
  const normalizedMessageKey = messageKey.trim();
  if (!normalizedMessageKey) {
    return null;
  }
  const escapedMessageKey = typeof CSS !== "undefined" && typeof CSS.escape === "function"
    ? CSS.escape(normalizedMessageKey)
    : normalizedMessageKey.replace(/["\\]/g, "\\$&");
  return document.querySelector<HTMLElement>(`[data-message-key="${escapedMessageKey}"]`);
}
