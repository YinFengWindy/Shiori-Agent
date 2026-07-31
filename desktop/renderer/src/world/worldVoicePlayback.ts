export type WorldVoiceProfile = Readonly<{
  configVersion?: string | number;
  config_version?: string | number;
  voiceId?: string;
  voice_id?: string;
  speed?: number;
  emotion?: string;
  enabled?: boolean;
  [key: string]: unknown;
}>;

export type WorldVoiceSynthesis = {
  audioBase64: string;
  format: "mp3";
};

export type WorldVoiceSynthesize = (
  text: string,
  voiceProfile: WorldVoiceProfile,
  signal: AbortSignal,
) => Promise<WorldVoiceSynthesis>;

export type WorldVoiceAudio = {
  onended: (() => void) | null;
  onerror: ((event: unknown) => void) | null;
  volume?: number;
  play(): Promise<void> | void;
  pause(): void;
  src?: string;
  load?: () => void;
};

export type WorldVoiceAudioFactory = (audioBase64: string, format: "mp3") => WorldVoiceAudio;

export type WorldVoiceCue = {
  cueId: string;
  worldId: string;
  text: string;
  voiceProfile?: WorldVoiceProfile | null;
};

export type WorldVoicePlaybackStatus = "played" | "fallback" | "skipped" | "cancelled" | "no_voice";

export type WorldVoicePlaybackOutcome = {
  cueId: string;
  status: WorldVoicePlaybackStatus;
  reason?: "no_voice_profile" | "synthesis_failed" | "playback_failed" | "invalid_audio" | "aborted";
};

export type WorldVoicePlaybackOptions = {
  synthesize: WorldVoiceSynthesize;
  createAudio: WorldVoiceAudioFactory;
  volume?: number;
  onPlaybackStart?: () => void;
  onPlaybackEnd?: () => void;
};

type NormalizedVoiceProfile = {
  version: string | number;
  voiceId: string;
  speed: number;
  emotion: string;
};

type QueueEntry = {
  cue: WorldVoiceCue;
  text: string;
  profile: NormalizedVoiceProfile;
  cacheKey: string;
  resolve: (outcome: WorldVoicePlaybackOutcome) => void;
};

type ActiveEntry = QueueEntry & {
  controller: AbortController;
  audio: WorldVoiceAudio | null;
  cancelStatus: "skipped" | "cancelled" | null;
  settled: boolean;
  resumePlayback: (() => void) | null;
  finishPlayback: (() => void) | null;
  generation: number;
};

/** Plays optional world dialogue voice audio without making speech a cue dependency. */
export class WorldVoicePlayback {
  private readonly cache = new Map<string, WorldVoiceSynthesis>();
  private readonly queue: QueueEntry[] = [];
  private readonly resumeWaiters = new Set<() => void>();
  private active: ActiveEntry | null = null;
  private paused = false;
  private pumping = false;
  private disposed = false;
  private generation = 0;
  private volume: number;

  constructor(private readonly options: WorldVoicePlaybackOptions) {
    this.volume = options.volume ?? 100;
  }

  /** Applies the current voice level without invalidating synthesized audio. */
  setVolume(volume: number): void {
    this.volume = Math.min(100, Math.max(0, volume));
    if (typeof this.active?.audio?.volume === "number") {
      this.active.audio.volume = normalizeVolume(this.volume);
    }
  }

  /** Queues one dialogue cue and resolves when audio or text fallback finishes. */
  playCue(cue: WorldVoiceCue): Promise<WorldVoicePlaybackOutcome> {
    if (this.disposed) return Promise.resolve({ cueId: cue.cueId, status: "cancelled", reason: "aborted" });

    const text = normalizeText(cue.text);
    const profile = normalizeVoiceProfile(cue.voiceProfile);
    if (!text || !profile) {
      return Promise.resolve({
        cueId: cue.cueId,
        status: "no_voice",
        reason: "no_voice_profile",
      });
    }

    return new Promise<WorldVoicePlaybackOutcome>((resolve) => {
      this.queue.push({
        cue,
        text,
        profile,
        cacheKey: createCacheKey(cue.worldId, profile, text),
        resolve,
      });
      void this.pump();
    });
  }

  /** Alias kept terse for callers that model playback as a normal queue. */
  enqueue(cue: WorldVoiceCue): Promise<WorldVoicePlaybackOutcome> {
    return this.playCue(cue);
  }

  /** Pauses the current audio and prevents the next queued cue from starting. */
  pause(): void {
    if (this.disposed || this.paused) return;
    this.paused = true;
    this.active?.audio?.pause();
  }

  /** Resumes the current audio or releases a queue paused before synthesis began. */
  resume(): void {
    if (this.disposed || !this.paused) return;
    this.paused = false;
    const waiters = [...this.resumeWaiters];
    this.resumeWaiters.clear();
    for (const resolve of waiters) resolve();
    this.active?.resumePlayback?.();
  }

  /** Skips only the current cue and continues with the remaining queue. */
  skip(): void {
    const active = this.active;
    if (!active) return;
    active.cancelStatus = "skipped";
    active.controller.abort();
    active.finishPlayback?.();
    this.destroyAudio(active.audio);
    this.settle(active, { cueId: active.cue.cueId, status: "skipped", reason: "aborted" });
  }

  /** Cancels the active cue and every queued cue. */
  cancel(): void {
    const active = this.active;
    for (const entry of this.queue.splice(0)) {
      entry.resolve({ cueId: entry.cue.cueId, status: "cancelled", reason: "aborted" });
    }
    if (!active) return;
    active.cancelStatus = "cancelled";
    active.controller.abort();
    active.finishPlayback?.();
    this.destroyAudio(active.audio);
    this.settle(active, { cueId: active.cue.cueId, status: "cancelled", reason: "aborted" });
  }

  /** Aborts outstanding synthesis, destroys audio, clears cache, and retires the player. */
  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.cancel();
    this.cache.clear();
    this.paused = false;
    for (const resolve of this.resumeWaiters) resolve();
    this.resumeWaiters.clear();
  }

  /** Clears synthesized audio so tests and callers can control cache lifetime explicitly. */
  clearCache(): void {
    this.cache.clear();
  }

  get cacheSize(): number {
    return this.cache.size;
  }

  get isDisposed(): boolean {
    return this.disposed;
  }

  private async pump(): Promise<void> {
    if (this.pumping || this.disposed || this.paused || this.active || this.queue.length === 0) return;
    this.pumping = true;
    try {
      while (!this.disposed && !this.paused && !this.active && this.queue.length > 0) {
        const entry = this.queue.shift();
        if (!entry) return;
        await this.process(entry);
      }
    } finally {
      this.pumping = false;
      if (!this.disposed && !this.paused && !this.active && this.queue.length > 0) void this.pump();
    }
  }

  private async process(entry: QueueEntry): Promise<void> {
    const active: ActiveEntry = {
      ...entry,
      controller: new AbortController(),
      audio: null,
      cancelStatus: null,
      settled: false,
      resumePlayback: null,
      finishPlayback: null,
      generation: ++this.generation,
    };
    this.active = active;

    try {
      const synthesized = this.cache.get(entry.cacheKey) ?? await this.synthesize(active);
      if (active.cancelStatus) return;
      if (!isValidSynthesis(synthesized)) {
        this.settle(active, { cueId: entry.cue.cueId, status: "fallback", reason: "invalid_audio" });
        return;
      }
      this.cache.set(entry.cacheKey, synthesized);
      await this.waitUntilResumed(active.controller.signal);
      if (active.cancelStatus || this.disposed) return;
      await this.playAudio(active, synthesized);
    } catch (error) {
      if (active.cancelStatus || active.controller.signal.aborted || this.disposed) return;
      this.settle(active, {
        cueId: entry.cue.cueId,
        status: "fallback",
        reason: error instanceof Error && error.name === "AbortError" ? "aborted" : "synthesis_failed",
      });
    } finally {
      active.resumePlayback = null;
      active.finishPlayback = null;
      this.destroyAudio(active.audio);
      if (this.active === active) this.active = null;
    }
  }

  private async synthesize(active: ActiveEntry): Promise<WorldVoiceSynthesis> {
    try {
      const synthesized = await this.options.synthesize(active.text, active.cue.voiceProfile as WorldVoiceProfile, active.controller.signal);
      if (active.cancelStatus || active.controller.signal.aborted) throw createAbortError();
      return synthesized;
    } catch (error) {
      if (active.cancelStatus || active.controller.signal.aborted) throw createAbortError();
      throw error;
    }
  }

  private async waitUntilResumed(signal: AbortSignal): Promise<void> {
    if (!this.paused) return;
    await new Promise<void>((resolve, reject) => {
      const onAbort = () => {
        this.resumeWaiters.delete(resolve);
        reject(createAbortError());
      };
      signal.addEventListener("abort", onAbort, { once: true });
      this.resumeWaiters.add(() => {
        signal.removeEventListener("abort", onAbort);
        this.resumeWaiters.delete(resolve);
        resolve();
      });
    });
  }

  private async playAudio(active: ActiveEntry, synthesized: WorldVoiceSynthesis): Promise<void> {
    const audio = this.options.createAudio(synthesized.audioBase64, synthesized.format);
    active.audio = audio;
    if (typeof audio.volume === "number") audio.volume = normalizeVolume(this.volume);
    const generation = active.generation;
    await new Promise<void>((resolve) => {
      let finished = false;
      const finish = (outcome: WorldVoicePlaybackOutcome): void => {
        if (finished || this.active !== active || active.generation !== generation) return;
        finished = true;
        active.resumePlayback = null;
        this.options.onPlaybackEnd?.();
        this.settle(active, outcome);
        resolve();
      };
      active.finishPlayback = () => finish({
        cueId: active.cue.cueId,
        status: active.cancelStatus ?? "cancelled",
        reason: "aborted",
      });
      audio.onended = () => finish({ cueId: active.cue.cueId, status: "played" });
      audio.onerror = () => finish({ cueId: active.cue.cueId, status: "fallback", reason: "playback_failed" });
      const start = (): void => {
        if (finished || active.cancelStatus || this.disposed) return;
        try {
          Promise.resolve(audio.play()).catch(() => finish({ cueId: active.cue.cueId, status: "fallback", reason: "playback_failed" }));
        } catch {
          finish({ cueId: active.cue.cueId, status: "fallback", reason: "playback_failed" });
        }
      };
      active.resumePlayback = start;
      this.options.onPlaybackStart?.();
      start();
    });
  }

  private settle(active: ActiveEntry, outcome: WorldVoicePlaybackOutcome): void {
    if (active.settled) return;
    active.settled = true;
    active.resolve(outcome);
  }

  private destroyAudio(audio: WorldVoiceAudio | null): void {
    if (!audio) return;
    audio.onended = null;
    audio.onerror = null;
    try {
      audio.pause();
    } catch {
      // Cleanup must not turn a text fallback into a playback exception.
    }
    if ("src" in audio) audio.src = "";
    try {
      audio.load?.();
    } catch {
      // Some test doubles and browsers reject load after an interrupted play.
    }
  }
}

function normalizeVolume(value: number): number {
  return Math.min(1, Math.max(0, value / 100));
}

function normalizeText(value: string): string {
  return String(value ?? "").trim().replace(/\s+/g, " ");
}

function normalizeVoiceProfile(profile: WorldVoiceProfile | null | undefined): NormalizedVoiceProfile | null {
  if (!profile || typeof profile !== "object" || profile.enabled === false) return null;
  const version = profile.configVersion ?? profile.config_version;
  const voiceId = String(profile.voiceId ?? profile.voice_id ?? "").trim();
  const speed = Number(profile.speed);
  const emotion = String(profile.emotion ?? "").trim();
  if ((typeof version !== "string" && typeof version !== "number") || String(version).trim() === "") return null;
  if (!voiceId || !Number.isFinite(speed) || speed < 0.5 || speed > 2) return null;
  return { version, voiceId, speed, emotion };
}

function createCacheKey(worldId: string, profile: NormalizedVoiceProfile, text: string): string {
  return JSON.stringify([worldId, profile.version, profile.voiceId, text, profile.speed, profile.emotion]);
}

function isValidSynthesis(value: WorldVoiceSynthesis): boolean {
  return Boolean(value)
    && value.format === "mp3"
    && typeof value.audioBase64 === "string"
    && value.audioBase64.length > 0;
}

function createAbortError(): Error {
  const error = new Error("voice playback aborted");
  error.name = "AbortError";
  return error;
}
