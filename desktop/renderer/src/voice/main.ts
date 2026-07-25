import { float32ToPcm16, resampleToVoiceRate } from "./captureAudio";

let stream: MediaStream | null = null;
let context: AudioContext | null = null;
let source: MediaStreamAudioSourceNode | null = null;
let processor: ScriptProcessorNode | null = null;
let mutedSink: GainNode | null = null;
let chunks: Float32Array[] = [];
let playbackContext: AudioContext | null = null;
let playbackSource: AudioBufferSourceNode | null = null;
let playbackId = "";
let ignorePlaybackEnd = false;

window.miraDesktop.onVoiceCaptureCommand((command) => {
  if (command === "start") {
    void startCapture();
    return;
  }
  if (command === "stop") {
    void stopCapture();
    return;
  }
  void cancelCapture();
});

window.miraDesktop.onVoicePlaybackCommand((command) => {
  if (command.command === "cancel") {
    cancelPlayback();
    return;
  }
  void playAudio(command.id, command.audioBase64);
});

async function playAudio(id: string, audioBase64: string): Promise<void> {
  try {
    cancelPlayback();
    playbackContext ??= new AudioContext();
    const audio = await playbackContext.decodeAudioData(decodeBase64(audioBase64));
    if (!playbackContext) return;
    const sourceNode = playbackContext.createBufferSource();
    sourceNode.buffer = audio;
    sourceNode.connect(playbackContext.destination);
    playbackSource = sourceNode;
    playbackId = id;
    ignorePlaybackEnd = false;
    sourceNode.onended = () => {
      if (ignorePlaybackEnd || playbackSource !== sourceNode || playbackId !== id) return;
      playbackSource = null;
      playbackId = "";
      window.miraDesktop.voicePlaybackFinished(id);
    };
    await playbackContext.resume();
    sourceNode.start();
    window.miraDesktop.voicePlaybackStarted(id);
  } catch (error) {
    playbackSource = null;
    playbackId = "";
    window.miraDesktop.voicePlaybackError(id, error instanceof Error ? error.message : "音频播放失败");
  }
}

function cancelPlayback(): void {
  ignorePlaybackEnd = true;
  try {
    playbackSource?.stop();
  } catch {
    // The source may already have ended between queue transitions.
  }
  playbackSource?.disconnect();
  playbackSource = null;
  playbackId = "";
}

function decodeBase64(value: string): ArrayBuffer {
  const binary = atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}

async function startCapture(): Promise<void> {
  try {
    await cancelCapture();
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    context = new AudioContext();
    source = context.createMediaStreamSource(stream);
    processor = context.createScriptProcessor(4096, 1, 1);
    mutedSink = context.createGain();
    mutedSink.gain.value = 0;
    chunks = [];
    processor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      chunks.push(input.slice());
    };
    source.connect(processor);
    processor.connect(mutedSink);
    mutedSink.connect(context.destination);
    window.miraDesktop.voiceCaptureReady();
  } catch (error) {
    window.miraDesktop.voiceCaptureError(error instanceof Error ? error.message : "没有可用的麦克风");
    await cancelCapture();
  }
}

async function stopCapture(): Promise<void> {
  try {
    const audio = collectPcm16();
    await cancelCapture();
    const transferable = new Uint8Array(audio.byteLength);
    transferable.set(new Uint8Array(audio.buffer, audio.byteOffset, audio.byteLength));
    window.miraDesktop.voiceCaptureData(transferable.buffer);
    window.miraDesktop.voiceCaptureStopped();
  } catch (error) {
    window.miraDesktop.voiceCaptureError(error instanceof Error ? error.message : "录音处理失败");
  }
}

async function cancelCapture(): Promise<void> {
  processor?.disconnect();
  source?.disconnect();
  mutedSink?.disconnect();
  stream?.getTracks().forEach((track) => track.stop());
  if (context) await context.close().catch(() => undefined);
  processor = null;
  source = null;
  mutedSink = null;
  context = null;
  stream = null;
  chunks = [];
}

function collectPcm16(): Int16Array {
  if (!context) throw new Error("麦克风尚未启动");
  const length = chunks.reduce((total, chunk) => total + Math.round(chunk.length * 16_000 / context!.sampleRate), 0);
  const output = new Int16Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    const pcm = float32ToPcm16(resampleToVoiceRate(chunk, context.sampleRate));
    output.set(pcm, offset);
    offset += pcm.length;
  }
  return output;
}
