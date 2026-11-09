/** An opaque, activation-bound native session; only the background host may open one. */
export type PluginNativeContext = { plugin_id: string; owner: string; generation: string };

/** A browser microphone exposed by the host's native audio surface. */
export type NativeAudioDevice = { deviceId: string; label: string };

/** One complete audio buffer; capture always returns 16 kHz mono WAV. */
export type NativeAudio = { audio_base64: string; format: "wav" | "mp3"; /** Optional caller correlation, echoed in playback observations. */ request_id?: string };

/** Owner-scoped observations from the host's actual output stream, via hostEvents. */
export const nativeAudioPlaybackEvent = "native.audio.playback";
/** RMS is measured from the playing Web Audio stream, clamped to [0, 1]; terminals are zero. */
export type NativeAudioPlaybackPayload = PluginNativeContext & {
  request_id?: string;
  playback_id: string;
  phase: "started" | "level" | "ended";
  amplitude: number;
  reason?: "finished" | "stopped" | "failed";
};

/** Scoped native resources, revoked when the owning background activation ends. */
export type PluginNativeApi = {
  audio: {
    devices(): Promise<NativeAudioDevice[]>;
    startCapture(deviceId?: string): Promise<void>;
    stopCapture(): Promise<NativeAudio>;
    cancelCapture(): Promise<void>;
    /** Resolves when this audio finishes or is stopped; no host playback queue. */
    play(audio: NativeAudio): Promise<void>;
    stop(): Promise<void>;
  };
  keys: {
    /** Rejects an accelerator the native key service cannot represent, without registering it. */
    validate(accelerator: string): Promise<void>;
    register(id: string, accelerator: string, listener: (phase: "down" | "up") => void): Promise<void>;
    unregister(id: string): Promise<void>;
  };
};

/** Narrow generic chat operations used by background consumers. */
export type PluginBackgroundChat = {
  send(request: { role_id: string; content: string; turn_id: string; media: string[] }): Promise<Record<string, unknown>>;
  cancel(request: { session_key: string; turn_id: string }): Promise<Record<string, unknown>>;
};
