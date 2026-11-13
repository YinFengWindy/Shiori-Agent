import type { PluginRpcClient, PluginServiceDescriptor, PluginServiceReference, TtsResult } from "@yinfengwindy/shiori-sdk";
import type { StoryBridgeClient } from "./storyBridgeClient";
import type { StoryDetails, StoryVoiceAudio } from "./types";

/** Public TTS service contract the Story discovers providers by. */
export const STORY_TTS_CONTRACT = "shiori.tts.v1";

/** One dialogue fragment the Story can voice. */
export type StoryVoiceLine = {
  beatId: string;
  fragmentIndex: number;
  text: string;
};

/** Where one voice line comes from and how it is cached. */
export type StoryVoiceSource = {
  /** Installed TTS providers the settings page offers. */
  listProviders(): Promise<PluginServiceDescriptor[]>;
  /**
   * Returns the line's audio: a recent result, the copy saved in the Story when
   * it came from the same provider, or a fresh synthesis that is then saved.
   * Concurrent calls for one line share a single provider request.
   */
  load(story: Pick<StoryDetails, "id" | "roleSnapshot" | "voices">, line: StoryVoiceLine, provider: PluginServiceReference): Promise<StoryVoiceAudio>;
};

type StoryVoiceSourceOptions = {
  rpc: Pick<PluginRpcClient, "services">;
  stories: Pick<StoryBridgeClient, "getVoice" | "saveVoice">;
  /** Reports a save failure; the synthesized audio still plays. */
  onSaveError: (cause: unknown) => void;
};

/** Recent lines kept in memory so replaying or going back needs no request. */
const RECENT_LINE_LIMIT = 12;

function sameProvider(left: PluginServiceReference, right: PluginServiceReference) {
  return left.plugin_id === right.plugin_id && left.service_id === right.service_id;
}

/** Creates the Story voice source over the TTS service and the Story's saved lines. */
export function createStoryVoiceSource({ rpc, stories, onSaveError }: StoryVoiceSourceOptions): StoryVoiceSource {
  const pending = new Map<string, Promise<StoryVoiceAudio>>();
  const recent = new Map<string, StoryVoiceAudio>();

  function remember(key: string, audio: StoryVoiceAudio) {
    recent.delete(key);
    recent.set(key, audio);
    if (recent.size > RECENT_LINE_LIMIT) recent.delete(recent.keys().next().value!);
  }

  async function resolve(story: Pick<StoryDetails, "id" | "roleSnapshot" | "voices">, line: StoryVoiceLine, provider: PluginServiceReference): Promise<StoryVoiceAudio> {
    const saved = story.voices.find((voice) => voice.beatId === line.beatId && voice.fragmentIndex === line.fragmentIndex);
    if (saved && sameProvider(saved.provider, provider)) {
      const stored = await stories.getVoice(story.id, line.beatId, line.fragmentIndex);
      if (stored && sameProvider(stored.provider, provider)) return { audio_base64: stored.audio_base64, format: stored.format };
    }
    const roleId = story.roleSnapshot.id?.trim() ?? "";
    if (!roleId) throw new Error("剧情角色缺少 ID，无法生成语音");
    const result = await rpc.services.call<TtsResult>(provider, "synthesize", { text: line.text, role_id: roleId, mood: "" });
    void stories.saveVoice(story.id, line.beatId, line.fragmentIndex, provider, result).catch(onSaveError);
    return { audio_base64: result.audio_base64, format: result.format };
  }

  return {
    async listProviders() {
      return (await rpc.services.list(STORY_TTS_CONTRACT)).services;
    },
    load(story, line, provider) {
      const key = `${story.id}:${line.beatId}:${line.fragmentIndex}:${provider.plugin_id}/${provider.service_id}`;
      const cached = recent.get(key);
      if (cached) return Promise.resolve(cached);
      const inFlight = pending.get(key);
      if (inFlight) return inFlight;
      const request = resolve(story, line, provider).then((audio) => {
        remember(key, audio);
        return audio;
      }).finally(() => pending.delete(key));
      pending.set(key, request);
      return request;
    },
  };
}

function decodeBase64(value: string): ArrayBuffer {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}

/**
 * Plays one voice line at a time through the Story's own audio graph, so the
 * Story volume applies and the host's single native playback slot stays free.
 */
export class StoryVoicePlayer {
  private context: AudioContext | null = null;
  private gain: GainNode | null = null;
  private current: { source: AudioBufferSourceNode; finish: () => void } | null = null;
  private volume = 1;

  /** Sets the volume in percent; it applies to the line already playing too. */
  setVolume(percent: number) {
    this.volume = Math.min(100, Math.max(0, percent)) / 100;
    if (this.gain) this.gain.gain.value = this.volume;
  }

  /** Plays `audio` after stopping any earlier line; resolves when it ends or is stopped. */
  async play(audio: StoryVoiceAudio, signal: AbortSignal): Promise<void> {
    this.stop();
    this.context ??= new AudioContext();
    if (!this.gain) {
      this.gain = this.context.createGain();
      this.gain.connect(this.context.destination);
    }
    this.gain.gain.value = this.volume;
    const buffer = await this.context.decodeAudioData(decodeBase64(audio.audio_base64));
    if (signal.aborted) return;
    if (this.context.state === "suspended") await this.context.resume();
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.gain);
    await new Promise<void>((resolveEnded) => {
      const finish = () => {
        signal.removeEventListener("abort", stopOnAbort);
        if (this.current?.source === source) this.current = null;
        resolveEnded();
      };
      const stopOnAbort = () => this.stop();
      source.onended = finish;
      signal.addEventListener("abort", stopOnAbort, { once: true });
      this.current = { source, finish };
      source.start();
    });
  }

  /** Stops the current line, if any. */
  stop() {
    const current = this.current;
    if (!current) return;
    this.current = null;
    current.source.onended = null;
    current.source.stop();
    current.finish();
  }

  /** Releases the audio context; a later `play` opens a new one. */
  dispose() {
    this.stop();
    const context = this.context;
    this.context = null;
    this.gain = null;
    if (context) void context.close();
  }
}
