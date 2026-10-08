/**
 * Sentences of one streamed chat reply, consumed by that reply's single
 * speech job. The job waits here between sentences so the reply holds the
 * speech line from its first sentence to its last.
 */
export class SentenceStream {
  private readonly items: string[] = [];
  private final = false;
  private closed = false;
  private wake: (() => void) | null = null;

  /** Appends sentences; `final` marks that no more will follow. */
  add(sentences: string[], final: boolean) {
    this.items.push(...sentences);
    if (final) this.final = true;
    this.notify();
  }

  /** Abandons the reply: the consumer's next read ends immediately. */
  close() { this.closed = true; this.notify(); }

  /** Next sentence, or null once the reply is complete, closed, or `signal` aborted. */
  async next(signal: AbortSignal): Promise<string | null> {
    for (;;) {
      if (this.closed || signal.aborted) return null;
      const item = this.items.shift();
      if (item !== undefined) return item;
      if (this.final) return null;
      await new Promise<void>((resolve) => {
        // Whichever fires first removes the other, so no listener outlives one wait.
        const done = () => { signal.removeEventListener("abort", done); this.wake = null; resolve(); };
        this.wake = done;
        signal.addEventListener("abort", done, { once: true });
      });
    }
  }

  private notify() {
    const wake = this.wake;
    this.wake = null;
    wake?.();
  }
}
