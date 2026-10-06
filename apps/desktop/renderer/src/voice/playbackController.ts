import type { VoicePlaybackCommand } from "../../../src/bridge/shared.js";

const PLAYBACK_RESUME_TIMEOUT_MS = 2_000;

type PlaybackAudioContext = Pick<AudioContext, "resume" | "state">;

/** Starts a hidden renderer's audio context or fails instead of hanging silently. */
export async function ensurePlaybackContextRunning(
  context: PlaybackAudioContext,
  timeoutMs = PLAYBACK_RESUME_TIMEOUT_MS,
): Promise<void> {
  if (context.state === "running") return;
  let timeout: ReturnType<typeof setTimeout> | null = null;
  try {
    await Promise.race([
      context.resume(),
      new Promise<never>((_resolve, reject) => {
        timeout = setTimeout(() => reject(new Error("音频播放被系统自动播放策略阻止")), timeoutMs);
      }),
    ]);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
  if ((context.state as AudioContextState) !== "running") {
    throw new Error("音频播放上下文未启动");
  }
}

/** Owns audio decoding and playback inside the hidden voice renderer. */
export class VoicePlaybackRenderer {
  private context: AudioContext | null = null;
  private source: AudioBufferSourceNode | null = null;
  private playbackId = "";
  private ignoreEnd = false;
  private generation = 0;

  handleCommand(command: VoicePlaybackCommand): void {
    if (command.command === "cancel") {
      this.cancel();
      return;
    }
    void this.play(command.id, command.audioBase64);
  }

  private async play(id: string, audioBase64: string): Promise<void> {
    this.cancel();
    const generation = this.generation;
    try {
      this.context ??= new AudioContext();
      const audio = await this.context.decodeAudioData(decodeBase64(audioBase64));
      if (!this.context || generation !== this.generation) return;
      const sourceNode = this.context.createBufferSource();
      sourceNode.buffer = audio;
      sourceNode.connect(this.context.destination);
      this.source = sourceNode;
      this.playbackId = id;
      this.ignoreEnd = false;
      sourceNode.onended = () => {
        if (this.ignoreEnd || this.source !== sourceNode || this.playbackId !== id) return;
        this.source = null;
        this.playbackId = "";
        window.miraDesktop.voicePlaybackFinished(id);
      };
      await ensurePlaybackContextRunning(this.context);
      if (generation !== this.generation) return;
      sourceNode.start();
      window.miraDesktop.voicePlaybackStarted(id);
    } catch (error) {
      if (generation !== this.generation) return;
      this.source = null;
      this.playbackId = "";
      window.miraDesktop.voicePlaybackError(id, error instanceof Error ? error.message : "音频播放失败");
    }
  }

  private cancel(): void {
    this.generation += 1;
    this.ignoreEnd = true;
    try {
      this.source?.stop();
    } catch {
      // The source may already have ended between queue transitions.
    }
    this.source?.disconnect();
    this.source = null;
    this.playbackId = "";
  }
}

function decodeBase64(value: string): ArrayBuffer {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}
