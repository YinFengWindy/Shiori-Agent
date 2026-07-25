import { float32ToPcm16, resampleToVoiceRate } from "./captureAudio";

let stream: MediaStream | null = null;
let context: AudioContext | null = null;
let source: MediaStreamAudioSourceNode | null = null;
let processor: ScriptProcessorNode | null = null;
let mutedSink: GainNode | null = null;
let chunks: Float32Array[] = [];

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
