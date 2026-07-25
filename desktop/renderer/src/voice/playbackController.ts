import type { VoicePlaybackCommand } from "../../../src/shared.js";

/** Owns audio decoding and playback inside the hidden voice renderer. */
export class VoicePlaybackRenderer {
  private context: AudioContext | null = null;
  private source: AudioBufferSourceNode | null = null;
  private playbackId = "";
  private ignoreEnd = false;

  handleCommand(command: VoicePlaybackCommand): void {
    if (command.command === "cancel") {
      this.cancel();
      return;
    }
    void this.play(command.id, command.audioBase64, true);
  }

  /** Plays a microphone test without reporting queue lifecycle events. */
  playTestAudio(audioBase64: string): void {
    void this.play("voice-test", audioBase64, false);
  }

  private async play(id: string, audioBase64: string, reportPlayback: boolean): Promise<void> {
    try {
      this.cancel();
      this.context ??= new AudioContext();
      const audio = await this.context.decodeAudioData(decodeBase64(audioBase64));
      if (!this.context) return;
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
        if (reportPlayback) window.miraDesktop.voicePlaybackFinished(id);
      };
      await this.context.resume();
      sourceNode.start();
      if (reportPlayback) window.miraDesktop.voicePlaybackStarted(id);
    } catch (error) {
      this.source = null;
      this.playbackId = "";
      if (reportPlayback) {
        window.miraDesktop.voicePlaybackError(id, error instanceof Error ? error.message : "音频播放失败");
      } else {
        window.miraDesktop.voiceCaptureError(error instanceof Error ? error.message : "试听播放失败");
      }
    }
  }

  private cancel(): void {
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
