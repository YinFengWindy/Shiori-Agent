import type { VoiceCaptureCommand } from "../../../src/shared.js";
import { float32ToPcm16, resampleToVoiceRate } from "./captureAudio";

/** Opens the configured microphone exactly once so a stale device id fails visibly. */
export function openVoiceInputStream(
  mediaDevices: Pick<MediaDevices, "getUserMedia">,
  deviceId?: string,
): Promise<MediaStream> {
  return mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      ...(deviceId ? { deviceId: { exact: deviceId } } : {}),
    },
  });
}

/** Owns microphone capture and device enumeration inside the hidden voice renderer. */
export class VoiceCaptureRenderer {
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private processor: ScriptProcessorNode | null = null;
  private mutedSink: GainNode | null = null;
  private chunks: Float32Array[] = [];

  handleCommand(command: VoiceCaptureCommand): boolean {
    if (command === "stop") {
      void this.stop();
      return true;
    }
    if (command === "cancel") {
      void this.cancel();
      return true;
    }
    if (command.command === "start") {
      void this.start(command.deviceId);
      return true;
    }
    if (command.command === "list-devices") {
      void this.listInputDevices();
      return true;
    }
    return false;
  }

  private async start(deviceId?: string): Promise<void> {
    try {
      await this.cancel();
      this.stream = await openVoiceInputStream(navigator.mediaDevices, deviceId);
      this.context = new AudioContext();
      this.source = this.context.createMediaStreamSource(this.stream);
      this.processor = this.context.createScriptProcessor(4096, 1, 1);
      this.mutedSink = this.context.createGain();
      this.mutedSink.gain.value = 0;
      this.chunks = [];
      this.processor.onaudioprocess = (event) => {
        this.chunks.push(event.inputBuffer.getChannelData(0).slice());
      };
      this.source.connect(this.processor);
      this.processor.connect(this.mutedSink);
      this.mutedSink.connect(this.context.destination);
      window.miraDesktop.voiceCaptureReady();
    } catch (error) {
      window.miraDesktop.voiceCaptureError(error instanceof Error ? error.message : "没有可用的麦克风");
      await this.cancel();
    }
  }

  private async listInputDevices(): Promise<void> {
    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      window.miraDesktop.voiceInputDevices(
        devices
          .filter((device) => device.kind === "audioinput")
          .map((device) => ({ deviceId: device.deviceId, label: device.label })),
      );
    } catch (error) {
      window.miraDesktop.voiceCaptureError(error instanceof Error ? error.message : "无法读取麦克风设备");
    }
  }

  private async stop(): Promise<void> {
    try {
      const audio = this.collectPcm16();
      await this.cancel();
      const transferable = new Uint8Array(audio.byteLength);
      transferable.set(new Uint8Array(audio.buffer, audio.byteOffset, audio.byteLength));
      window.miraDesktop.voiceCaptureData(transferable.buffer);
      window.miraDesktop.voiceCaptureStopped();
    } catch (error) {
      window.miraDesktop.voiceCaptureError(error instanceof Error ? error.message : "录音处理失败");
    }
  }

  private async cancel(): Promise<void> {
    this.processor?.disconnect();
    this.source?.disconnect();
    this.mutedSink?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    if (this.context) await this.context.close().catch(() => undefined);
    this.processor = null;
    this.source = null;
    this.mutedSink = null;
    this.context = null;
    this.stream = null;
    this.chunks = [];
  }

  private collectPcm16(): Int16Array {
    if (!this.context) throw new Error("麦克风尚未启动");
    const length = this.chunks.reduce(
      (total, chunk) => total + Math.round(chunk.length * 16_000 / this.context!.sampleRate),
      0,
    );
    const output = new Int16Array(length);
    let offset = 0;
    for (const chunk of this.chunks) {
      const pcm = float32ToPcm16(resampleToVoiceRate(chunk, this.context.sampleRate));
      output.set(pcm, offset);
      offset += pcm.length;
    }
    return output;
  }
}
