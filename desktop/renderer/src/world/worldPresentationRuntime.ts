import type { PresentationCue } from "./presentationProtocol";
import { createBrowserVoiceAudio, createBrowserWorldAudio } from "./worldBrowserAudioAdapters";
import { WorldAudioMixer, type WorldAudioFactory } from "./worldAudioMixer";
import { WorldDialogueGate } from "./worldDialogueGate";
import { readWorldGameSettings, type WorldGameSettings } from "./worldGameSettingsStore";
import {
  WorldVoicePlayback,
  type WorldVoiceAudioFactory,
  type WorldVoiceCue,
  type WorldVoiceProfile,
  type WorldVoiceSynthesize,
} from "./worldVoicePlayback";

export type WorldPresentationRuntimeOptions = {
  synthesizeVoice?: WorldVoiceSynthesize;
  createWorldAudio?: WorldAudioFactory;
  createVoiceAudio?: WorldVoiceAudioFactory;
  readSettings?: () => WorldGameSettings;
};

type RetainedStageResource = {
  key: string;
  value: unknown;
  dispose: (value: unknown) => void;
};

/** Owns World audio, dialogue gates, caches, and stage resources across view changes. */
export class WorldPresentationRuntime {
  readonly #dialogue: WorldDialogueGate;
  readonly #audioMixer: WorldAudioMixer;
  readonly #voicePlayback: WorldVoicePlayback | null;
  readonly #readSettings: () => WorldGameSettings;
  #stageResource: RetainedStageResource | null = null;
  readonly #readDialogueCueIds = new Set<string>();
  #disposed = false;

  constructor(options: WorldPresentationRuntimeOptions = {}) {
    this.#readSettings = options.readSettings ?? readWorldGameSettings;
    const settings = this.#readSettings();
    this.#dialogue = new WorldDialogueGate(settings);
    this.#audioMixer = new WorldAudioMixer({
      createAudio: options.createWorldAudio ?? createBrowserWorldAudio,
      musicVolume: settings.musicVolume,
      ambienceVolume: settings.ambienceVolume,
      effectsVolume: settings.effectsVolume,
    });
    this.#voicePlayback = options.synthesizeVoice ? new WorldVoicePlayback({
      synthesize: options.synthesizeVoice,
      createAudio: options.createVoiceAudio ?? createBrowserVoiceAudio,
      volume: settings.voiceVolume,
      onPlaybackStart: () => this.#audioMixer.voiceStarted(),
      onPlaybackEnd: () => this.#audioMixer.voiceEnded(),
    }) : null;
  }

  /** Returns the stable dialogue state used by the React interaction layer. */
  dialogueSnapshot() {
    return this.#dialogue.snapshot();
  }

  /** Subscribes to active dialogue changes. */
  subscribeDialogue(listener: () => void) {
    return this.#dialogue.subscribe(listener);
  }

  /** Refreshes persisted settings while preserving caches and active resources. */
  refreshSettings(): WorldGameSettings {
    const settings = this.#readSettings();
    this.#dialogue.updateSettings(settings);
    this.#audioMixer.setVolumes({
      music: settings.musicVolume,
      ambience: settings.ambienceVolume,
      effects: settings.effectsVolume,
    });
    this.#voicePlayback?.setVolume(settings.voiceVolume);
    return settings;
  }

  /** Plays audio side effects and blocks dialogue cues at the user-advance seam. */
  handleRenderedCue(cue: PresentationCue, worldId: string): Promise<void> | void {
    this.#assertActive();
    this.#audioMixer.playCue(cue);
    if (cue.kind !== "dialogue") return;
    const voiceCue = voiceCueForPresentation(cue, worldId);
    const voiceFinished = voiceCue ? this.#voicePlayback?.playCue(voiceCue) : undefined;
    const text = cueText(cue);
    if (!text) return;
    const completion = this.#dialogue.present({
      cueId: cue.cueId,
      text,
      speakerName: cueSpeakerName(cue),
      voiceFinished,
      stopVoice: () => this.#voicePlayback?.skip(),
    });
    return completion;
  }

  /** Reveals or advances the active dialogue according to the current gate state. */
  continueDialogue() {
    const cueId = this.#dialogue.snapshot().cueId;
    const result = this.#dialogue.continue();
    if (cueId && result === "advanced") this.#readDialogueCueIds.add(cueId);
    return result;
  }

  /** Skips the current dialogue voice and releases the cue waiter. */
  skipDialogue(force = false): void {
    const snapshot = this.#dialogue.snapshot();
    if (!force && snapshot.cueId && this.#readSettings().skipReadTextOnly && !this.#readDialogueCueIds.has(snapshot.cueId)) {
      if (!snapshot.fullyRevealed) {
        this.#dialogue.continue();
        return;
      }
      this.#readDialogueCueIds.add(snapshot.cueId);
    }
    this.#dialogue.skip();
    this.#voicePlayback?.skip();
  }

  /** Pauses every presentation-owned clock and audio channel. */
  pause(): void {
    this.#dialogue.pause();
    this.#voicePlayback?.pause();
    this.#audioMixer.pause();
  }

  /** Resumes presentation-owned clocks and audio channels. */
  resume(): void {
    this.#dialogue.resume();
    this.#voicePlayback?.resume();
    this.#audioMixer.resume();
  }

  /** Retains one renderer-specific cache until the World route exits. */
  retainStageResource<T>(key: string, create: () => T, dispose: (value: T) => void): T {
    this.#assertActive();
    if (this.#stageResource?.key === key) return this.#stageResource.value as T;
    if (this.#stageResource) this.#stageResource.dispose(this.#stageResource.value);
    const value = create();
    this.#stageResource = {
      key,
      value,
      dispose: (resource) => dispose(resource as T),
    };
    return value;
  }

  /** Releases all resources exactly once when leaving the World application surface. */
  dispose(): void {
    if (this.#disposed) return;
    this.#disposed = true;
    this.#dialogue.dispose();
    this.#voicePlayback?.dispose();
    this.#audioMixer.dispose();
    if (this.#stageResource) this.#stageResource.dispose(this.#stageResource.value);
    this.#stageResource = null;
    this.#readDialogueCueIds.clear();
  }

  #assertActive(): void {
    if (this.#disposed) throw new Error("world presentation runtime is disposed");
  }
}

function cueSpeakerName(cue: PresentationCue): string {
  const value = cue.payload.speakerName ?? cue.payload.speaker_name ?? cue.payload.speaker;
  return typeof value === "string" ? value : "";
}

function cueText(cue: PresentationCue): string {
  const value = cue.payload.content ?? cue.payload.text;
  return typeof value === "string" ? value : "";
}

function voiceCueForPresentation(cue: PresentationCue, worldId: string): WorldVoiceCue | null {
  const text = cueText(cue);
  if (!text) return null;
  const profile = cue.payload.voiceProfile;
  return {
    cueId: cue.cueId,
    worldId,
    text,
    voiceProfile: typeof profile === "object" && profile !== null && !Array.isArray(profile)
      ? profile as WorldVoiceProfile
      : null,
  };
}
