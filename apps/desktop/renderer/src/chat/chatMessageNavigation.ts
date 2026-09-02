type ChatMessageNavigationWatcherOptions = {
  findTarget: () => HTMLElement | null;
  onTarget: (target: HTMLElement) => void;
  requestAnimationFrame: (callback: FrameRequestCallback) => number;
  cancelAnimationFrame: (handle: number) => void;
  setTimeout: (callback: () => void, delayMs: number) => number;
  clearTimeout: (handle: number) => void;
  observeMutations: (callback: () => void) => () => void;
  retryDelayMs?: number;
};

/** Watches for a virtualized chat message to mount and stops after locating it. */
export function watchForChatMessageTarget({
  findTarget,
  onTarget,
  requestAnimationFrame,
  cancelAnimationFrame,
  setTimeout,
  clearTimeout,
  observeMutations,
  retryDelayMs = 80,
}: ChatMessageNavigationWatcherOptions): () => void {
  let stopped = false;
  let frameHandle: number | null = null;
  let timeoutHandle: number | null = null;
  let stopObserving: () => void = () => undefined;

  const stop = () => {
    if (stopped) return;
    stopped = true;
    if (frameHandle !== null) {
      cancelAnimationFrame(frameHandle);
      frameHandle = null;
    }
    if (timeoutHandle !== null) {
      clearTimeout(timeoutHandle);
      timeoutHandle = null;
    }
    stopObserving();
  };

  const attempt = () => {
    if (stopped) return;
    const target = findTarget();
    if (target) {
      stop();
      onTarget(target);
      return;
    }
    if (timeoutHandle !== null) return;
    timeoutHandle = setTimeout(() => {
      timeoutHandle = null;
      attempt();
    }, retryDelayMs);
  };

  stopObserving = observeMutations(attempt);
  frameHandle = requestAnimationFrame(() => {
    frameHandle = null;
    attempt();
  });

  return stop;
}
