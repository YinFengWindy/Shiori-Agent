export const chatScrollAnimationMinDurationMs = 320;
export const chatScrollAnimationMaxDurationMs = 900;
export const chatScrollAnimationPixelsPerMs = 2;
export const chatScrollBottomThreshold = 24;

export type ChatSessionScrollState = {
  scrollTop: number;
  wasAtBottom: boolean;
};

/** Returns the current scrollable bottom, including any newly measured content. */
export function getChatScrollMaxTop(container: HTMLDivElement): number {
  return Math.max(0, container.scrollHeight - container.clientHeight);
}

/** Captures a session's scroll position and whether it was anchored to the bottom. */
export function captureChatSessionScrollState(
  scrollTop: number,
  scrollHeight: number,
  clientHeight: number,
): ChatSessionScrollState {
  const maxTop = Math.max(0, scrollHeight - clientHeight);
  const normalizedTop = Math.max(0, Math.min(scrollTop, maxTop));
  return {
    scrollTop: normalizedTop,
    wasAtBottom: maxTop - normalizedTop <= chatScrollBottomThreshold,
  };
}

/** Records a shared chat container under the session that currently owns it. */
export function rememberChatSessionScrollState(
  states: Map<string, ChatSessionScrollState>,
  sessionKey: string,
  scrollTop: number,
  scrollHeight: number,
  clientHeight: number,
): void {
  if (!sessionKey) return;
  states.set(
    sessionKey,
    captureChatSessionScrollState(scrollTop, scrollHeight, clientHeight),
  );
}

/** Resolves a saved session position against the destination container's current height. */
export function getChatSessionRestoreScrollTop(
  state: ChatSessionScrollState,
  scrollHeight: number,
  clientHeight: number,
): number {
  const maxTop = Math.max(0, scrollHeight - clientHeight);
  return state.wasAtBottom
    ? maxTop
    : Math.max(0, Math.min(state.scrollTop, maxTop));
}

/** Scales long bottom jumps without making short jumps feel sluggish. */
export function getChatScrollAnimationDuration(distance: number): number {
  return Math.min(
    chatScrollAnimationMaxDurationMs,
    Math.max(chatScrollAnimationMinDurationMs, distance / chatScrollAnimationPixelsPerMs),
  );
}

/** Applies a cubic ease-out curve to one bottom-scroll frame. */
export function getChatScrollAnimationTop(
  startTop: number,
  targetTop: number,
  progress: number,
): number {
  const easedProgress = 1 - ((1 - progress) ** 3);
  return startTop + (targetTop - startTop) * easedProgress;
}
