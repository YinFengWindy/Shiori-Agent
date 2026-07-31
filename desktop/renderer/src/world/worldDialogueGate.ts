export type WorldDialogueGateSettings = {
  showFullText: boolean;
  autoPlay: boolean;
  autoPlayDelayMs: number;
  textSpeed?: "slow" | "normal" | "fast";
};

export type WorldDialoguePresentation = {
  cueId: string;
  text: string;
  speakerName?: string;
  voiceFinished?: Promise<unknown>;
  stopVoice?: () => void;
};

export type WorldDialogueSnapshot = {
  cueId: string | null;
  text: string;
  visibleText: string;
  speakerName: string;
  fullyRevealed: boolean;
  paused: boolean;
};

type Schedule = (callback: () => void, delayMs: number) => () => void;

const emptySnapshot: WorldDialogueSnapshot = {
  cueId: null,
  text: "",
  visibleText: "",
  speakerName: "",
  fullyRevealed: true,
  paused: false,
};

const scheduleTimeout: Schedule = (callback, delayMs) => {
  const timeout = globalThis.setTimeout(callback, delayMs);
  return () => globalThis.clearTimeout(timeout);
};

/** Serializes dialogue reveal, manual advance, voice completion, and auto-play. */
export class WorldDialogueGate {
  readonly #listeners = new Set<() => void>();
  readonly #schedule: Schedule;
  #settings: WorldDialogueGateSettings;
  #snapshot = emptySnapshot;
  #active: (WorldDialoguePresentation & { resolve: () => void; revealIndex: number; voiceComplete: boolean }) | null = null;
  #cancelScheduledAdvance: (() => void) | null = null;
  #cancelScheduledReveal: (() => void) | null = null;

  constructor(settings: WorldDialogueGateSettings, schedule: Schedule = scheduleTimeout) {
    this.#settings = settings;
    this.#schedule = schedule;
  }

  /** Returns the current immutable dialogue view. */
  snapshot(): WorldDialogueSnapshot {
    return this.#snapshot;
  }

  /** Subscribes React or tests to dialogue state changes. */
  subscribe(listener: () => void) {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  }

  /** Applies current desktop preferences without interrupting the active line. */
  updateSettings(settings: WorldDialogueGateSettings): void {
    this.#settings = settings;
  }

  /** Presents one blocking dialogue cue until manual or automatic advancement. */
  present(dialogue: WorldDialoguePresentation): Promise<void> {
    if (this.#active) throw new Error("a world dialogue cue is already active");
    return new Promise<void>((resolve) => {
      const fullyRevealed = this.#settings.showFullText || dialogue.text.length <= 1;
      const revealIndex = fullyRevealed ? dialogue.text.length : 1;
      this.#active = { ...dialogue, resolve, revealIndex, voiceComplete: !dialogue.voiceFinished };
      this.#snapshot = {
        cueId: dialogue.cueId,
        text: dialogue.text,
        visibleText: dialogue.text.slice(0, revealIndex),
        speakerName: dialogue.speakerName ?? "",
        fullyRevealed,
        paused: false,
      };
      this.#emit();
      if (!fullyRevealed) this.#scheduleReveal(dialogue.cueId);
      void Promise.resolve(dialogue.voiceFinished).catch(() => undefined).then(() => {
        if (this.#active?.cueId !== dialogue.cueId) return;
        this.#active.voiceComplete = true;
        this.#tryScheduleAutoAdvance(dialogue.cueId);
      });
    });
  }

  /** Reveals first, then advances and stops any remaining voice playback. */
  continue(): "idle" | "revealed" | "advanced" {
    if (!this.#active || this.#snapshot.paused) return "idle";
    if (!this.#snapshot.fullyRevealed) {
      this.#cancelScheduledReveal?.();
      this.#cancelScheduledReveal = null;
      if (this.#active) this.#active.revealIndex = this.#active.text.length;
      this.#snapshot = { ...this.#snapshot, visibleText: this.#snapshot.text, fullyRevealed: true };
      this.#emit();
      this.#tryScheduleAutoAdvance(this.#snapshot.cueId ?? "");
      return "revealed";
    }
    this.#complete(this.#active.cueId, true);
    return "advanced";
  }

  /** Skips the active dialogue and releases its playback waiter. */
  skip(): void {
    if (this.#active) this.#complete(this.#active.cueId, true);
  }

  /** Pauses manual and scheduled advancement without discarding the line. */
  pause(): void {
    if (!this.#active || this.#snapshot.paused) return;
    this.#cancelScheduledAdvance?.();
    this.#cancelScheduledAdvance = null;
    this.#cancelScheduledReveal?.();
    this.#cancelScheduledReveal = null;
    this.#snapshot = { ...this.#snapshot, paused: true };
    this.#emit();
  }

  /** Resumes the active line; auto-play waits a fresh configured interval. */
  resume(): void {
    const cueId = this.#active?.cueId;
    if (!cueId || !this.#snapshot.paused) return;
    this.#snapshot = { ...this.#snapshot, paused: false };
    this.#emit();
    if (this.#settings.autoPlay) {
      this.#tryScheduleAutoAdvance(cueId);
    }
    if (!this.#snapshot.fullyRevealed) this.#scheduleReveal(cueId);
  }

  /** Cancels the current waiter and removes every subscriber. */
  dispose(): void {
    this.skip();
    this.#listeners.clear();
  }

  #complete(cueId: string, stopVoice: boolean): void {
    if (this.#active?.cueId !== cueId) return;
    const active = this.#active;
    this.#active = null;
    this.#cancelScheduledAdvance?.();
    this.#cancelScheduledAdvance = null;
    this.#cancelScheduledReveal?.();
    this.#cancelScheduledReveal = null;
    if (stopVoice) active.stopVoice?.();
    this.#snapshot = emptySnapshot;
    this.#emit();
    active.resolve();
  }

  #emit(): void {
    for (const listener of this.#listeners) listener();
  }

  #scheduleReveal(cueId: string): void {
    if (this.#snapshot.paused || this.#active?.cueId !== cueId) return;
    const delay = this.#settings.textSpeed === "slow" ? 55 : this.#settings.textSpeed === "fast" ? 18 : 32;
    this.#cancelScheduledReveal = this.#schedule(() => {
      const active = this.#active;
      if (!active || active.cueId !== cueId || this.#snapshot.paused) return;
      active.revealIndex = Math.min(active.text.length, active.revealIndex + 1);
      const fullyRevealed = active.revealIndex >= active.text.length;
      this.#snapshot = {
        ...this.#snapshot,
        visibleText: active.text.slice(0, active.revealIndex),
        fullyRevealed,
      };
      this.#emit();
      if (fullyRevealed) {
        this.#cancelScheduledReveal = null;
        this.#tryScheduleAutoAdvance(cueId);
      } else {
        this.#scheduleReveal(cueId);
      }
    }, delay);
  }

  #tryScheduleAutoAdvance(cueId: string): void {
    const active = this.#active;
    if (!this.#settings.autoPlay || !active || active.cueId !== cueId) return;
    if (this.#snapshot.paused || !this.#snapshot.fullyRevealed || !active.voiceComplete) return;
    this.#cancelScheduledAdvance?.();
    this.#cancelScheduledAdvance = this.#schedule(
      () => this.#complete(cueId, false),
      this.#settings.autoPlayDelayMs,
    );
  }
}
