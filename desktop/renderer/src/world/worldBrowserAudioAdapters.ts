import type { WorldAudioElement } from "./worldAudioMixer";
import type { WorldVoiceAudio } from "./worldVoicePlayback";

/** Adapts an opaque World audio URL to the non-dialogue mixer interface. */
export function createBrowserWorldAudio(url: string): WorldAudioElement {
  const audio = new Audio(url);
  return {
    get currentTime() { return audio.currentTime; },
    set currentTime(value) { audio.currentTime = value; },
    get loop() { return audio.loop; },
    set loop(value) { audio.loop = value; },
    get volume() { return audio.volume; },
    set volume(value) { audio.volume = value; },
    get onended() { return audio.onended as (() => void) | null; },
    set onended(handler) { audio.onended = handler; },
    get onerror() { return audio.onerror as ((event: unknown) => void) | null; },
    set onerror(handler) { audio.onerror = handler as OnErrorEventHandler; },
    play: () => audio.play(),
    pause: () => audio.pause(),
    load: () => audio.load(),
    get src() { return audio.src; },
    set src(value) { audio.src = value; },
  };
}

/** Adapts synthesized MP3 bytes to the dialogue voice interface. */
export function createBrowserVoiceAudio(audioBase64: string): WorldVoiceAudio {
  const audio = new Audio(`data:audio/mpeg;base64,${audioBase64}`);
  return {
    get onended() { return audio.onended as (() => void) | null; },
    set onended(handler) { audio.onended = handler; },
    get onerror() { return audio.onerror as ((event: unknown) => void) | null; },
    set onerror(handler) { audio.onerror = handler as OnErrorEventHandler; },
    get volume() { return audio.volume; },
    set volume(value) { audio.volume = value; },
    get src() { return audio.src; },
    set src(value) { audio.src = value; },
    play: () => audio.play(),
    pause: () => audio.pause(),
    load: () => audio.load(),
  };
}
