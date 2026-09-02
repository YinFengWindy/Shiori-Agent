export const chatScrollAnimationMinDurationMs = 320;
export const chatScrollAnimationMaxDurationMs = 900;
export const chatScrollAnimationPixelsPerMs = 2;

/** Returns the current scrollable bottom, including any newly measured content. */
export function getChatScrollMaxTop(container: HTMLDivElement): number {
  return Math.max(0, container.scrollHeight - container.clientHeight);
}

/** Uses instant positioning for the first session and smooth positioning for session switches. */
export function getChatSessionResetScrollBehavior(previousSessionKey: string, sessionKey: string) {
  return previousSessionKey && sessionKey && previousSessionKey !== sessionKey ? "smooth" : "auto";
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
