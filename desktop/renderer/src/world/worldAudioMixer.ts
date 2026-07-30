import type { PresentationCue } from "./presentationProtocol";

export type WorldAudioChannel = "music" | "ambience" | "effects";

export type WorldAudioElement = {
  currentTime: number;
  loop: boolean;
  volume: number;
  onended: (() => void) | null;
  onerror: ((event: unknown) => void) | null;
  play(): Promise<void> | void;
  pause(): void;
  load?(): void;
  src?: string;
};

export type WorldAudioFactory = (url: string) => WorldAudioElement;

export type WorldAudioMixerOptions = {
  createAudio: WorldAudioFactory;
  musicVolume?: number;
  ambienceVolume?: number;
  effectsVolume?: number;
  voiceDuckFactor?: number;
};

type ActiveAudio = {
  audio: WorldAudioElement;
  channel: WorldAudioChannel;
};

/** Coordinates non-dialogue World audio and restores channel levels after voice ducking. */
export class WorldAudioMixer {
  private readonly channels: Record<WorldAudioChannel, number>;
  private readonly createAudio: WorldAudioFactory;
  private readonly voiceDuckFactor: number;
  private readonly active = new Map<WorldAudioChannel, ActiveAudio>();
  private disposed = false;
  private voiceActive = 0;

  constructor(options: WorldAudioMixerOptions) {
    this.channels = {
      music: normalizeVolume(options.musicVolume ?? 70),
      ambience: normalizeVolume(options.ambienceVolume ?? 70),
      effects: normalizeVolume(options.effectsVolume ?? 80),
    };
    this.createAudio = options.createAudio;
    this.voiceDuckFactor = Math.min(1, Math.max(0, options.voiceDuckFactor ?? 0.55));
  }

  /** Starts audio cues without making background music or ambience block dialogue. */
  playCue(cue: PresentationCue): void {
    if (this.disposed || cue.kind !== "audio") return;
    const items = Array.isArray(cue.payload.items) ? cue.payload.items : [cue.payload];
    for (const item of items) {
      if (!item || typeof item !== "object" || Array.isArray(item)) continue;
      const value = item as Record<string, unknown>;
      const url = [value.audioUrl, value.audio_url, value.url]
        .find((candidate): candidate is string => typeof candidate === "string" && candidate.startsWith("shiori-asset://"));
      if (!url) continue;
      const channel = normalizeChannel(value.channel ?? value.kind);
      this.stopChannel(channel);
      const audio = this.createAudio(url);
      const active = { audio, channel };
      this.active.set(channel, active);
      audio.loop = value.loop === true || channel !== "effects";
      audio.volume = this.effectiveVolume(channel);
      audio.onended = () => {
        if (this.active.get(channel) === active) this.active.delete(channel);
      };
      audio.onerror = () => {
        if (this.active.get(channel) === active) this.active.delete(channel);
      };
      try {
        Promise.resolve(audio.play()).catch(() => audio.onerror?.(new Error("audio playback failed")));
      } catch {
        audio.onerror?.(new Error("audio playback failed"));
      }
    }
  }

  /** Applies a stable volume multiplier while one or more dialogue voices are audible. */
  voiceStarted(): void {
    if (this.disposed) return;
    this.voiceActive += 1;
    this.refreshVolumes();
  }

  voiceEnded(): void {
    if (this.voiceActive === 0) return;
    this.voiceActive -= 1;
    this.refreshVolumes();
  }

  /** Applies persisted channel levels to active and future audio. */
  setVolumes(levels: Partial<Record<WorldAudioChannel, number>>): void {
    if (this.disposed) return;
    for (const channel of ["music", "ambience", "effects"] as const) {
      const level = levels[channel];
      if (typeof level === "number") this.channels[channel] = normalizeVolume(level);
    }
    this.refreshVolumes();
  }

  pause(): void {
    this.active.forEach(({ audio }) => audio.pause());
  }

  resume(): void {
    if (this.disposed) return;
    this.active.forEach(({ audio }) => {
      try {
        Promise.resolve(audio.play()).catch(() => undefined);
      } catch {
        // A rejected autoplay resume should not interrupt the World cue queue.
      }
    });
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.active.forEach(({ audio }) => {
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      if ("src" in audio) audio.src = "";
      audio.load?.();
    });
    this.active.clear();
  }

  private stopChannel(channel: WorldAudioChannel): void {
    const current = this.active.get(channel);
    if (!current) return;
    current.audio.onended = null;
    current.audio.onerror = null;
    current.audio.pause();
    if ("src" in current.audio) current.audio.src = "";
    current.audio.load?.();
    this.active.delete(channel);
  }

  private refreshVolumes(): void {
    this.active.forEach(({ audio, channel }) => {
      audio.volume = this.effectiveVolume(channel);
    });
  }

  private effectiveVolume(channel: WorldAudioChannel): number {
    const base = this.channels[channel];
    return channel === "effects" || this.voiceActive === 0 ? base : base * this.voiceDuckFactor;
  }
}

function normalizeVolume(value: number): number {
  return Math.min(1, Math.max(0, value / 100));
}

function normalizeChannel(value: unknown): WorldAudioChannel {
  const channel = String(value ?? "effects").toLowerCase();
  if (channel === "music" || channel === "bgm") return "music";
  if (channel === "ambience" || channel === "ambient" || channel === "environment") return "ambience";
  return "effects";
}
