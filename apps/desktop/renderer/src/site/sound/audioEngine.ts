import { SFX_RECIPES, shouldPlayBgm, volumeToGain, type SfxName } from "./soundModel";

/** Everything the engine needs from the visitor's prefs plus the configured track. */
export interface SoundSettings {
  readonly soundEnabled: boolean;
  readonly sfxVolume: number;
  readonly bgmVolume: number;
  readonly track: string | null;
}

/** Seconds for the master / BGM fades and for live volume changes. */
const MASTER_FADE_S = 0.25;
const BGM_FADE_IN_S = 1.2;
const BGM_FADE_OUT_S = 0.6;
const LIVE_CHANGE_S = 0.05;

interface Graph {
  readonly context: AudioContext;
  readonly master: GainNode;
  readonly sfx: GainNode;
  readonly bgm: GainNode;
}

function sameSettings(a: SoundSettings, b: SoundSettings) {
  return a.soundEnabled === b.soundEnabled && a.sfxVolume === b.sfxVolume && a.bgmVolume === b.bgmVolume && a.track === b.track;
}

/** Glide a gain to `value` over roughly `seconds` from now. */
function rampTo(param: AudioParam, context: AudioContext, value: number, seconds: number) {
  param.cancelScheduledValues(context.currentTime);
  param.setValueAtTime(param.value, context.currentTime);
  param.linearRampToValueAtTime(value, context.currentTime + seconds);
}

/**
 * The site's WebAudio engine: master → (sfx, bgm) gain nodes, synthesized
 * SFX voices and one looping `<audio>` element for BGM routed through the
 * graph. The AudioContext is only created by `unlock()`, which callers must
 * invoke from a user gesture (autoplay policy); before that `sync` just
 * remembers settings and `playSfx` is silent. With no track configured no
 * `<audio>` element exists, so nothing is ever fetched.
 */
export function createAudioEngine(createContext: () => AudioContext = () => new AudioContext()) {
  let graph: Graph | null = null;
  let settings: SoundSettings | null = null;
  let bgmElement: HTMLAudioElement | null = null;
  let bgmPlaying = false;
  let pauseTimer: ReturnType<typeof setTimeout> | undefined;

  function startBgm(current: Graph, track: string) {
    if (!bgmElement) {
      bgmElement = new Audio(track);
      bgmElement.loop = true;
      current.context.createMediaElementSource(bgmElement).connect(current.bgm);
    }
    clearTimeout(pauseTimer);
    bgmPlaying = true;
    // A rejected play() (e.g. a missing file) leaves BGM off without
    // breaking SFX; the next sync retries.
    bgmElement.play().catch(() => {
      bgmPlaying = false;
    });
  }

  function stopBgm(current: Graph) {
    bgmPlaying = false;
    rampTo(current.bgm.gain, current.context, 0, BGM_FADE_OUT_S);
    clearTimeout(pauseTimer);
    pauseTimer = setTimeout(() => bgmElement?.pause(), BGM_FADE_OUT_S * 1000);
  }

  /** Apply settings to the live graph: master fade, SFX level, BGM start/stop/volume. */
  function apply(current: Graph, next: SoundSettings) {
    const { context } = current;
    rampTo(current.master.gain, context, next.soundEnabled ? 1 : 0, MASTER_FADE_S);
    rampTo(current.sfx.gain, context, volumeToGain(next.sfxVolume), LIVE_CHANGE_S);
    const wantBgm = shouldPlayBgm({ ...next, hasContext: true });
    if (wantBgm && next.track !== null) {
      const fadeIn = !bgmPlaying;
      if (fadeIn) startBgm(current, next.track);
      rampTo(current.bgm.gain, context, volumeToGain(next.bgmVolume), fadeIn ? BGM_FADE_IN_S : LIVE_CHANGE_S);
    } else if (bgmPlaying) {
      stopBgm(current);
    }
  }

  return {
    /** True once `unlock()` has created the AudioContext. */
    get unlocked() {
      return graph !== null;
    },

    /** Create (or resume) the AudioContext. Call only from a user gesture. */
    unlock() {
      if (!graph) {
        const context = createContext();
        const master = context.createGain();
        const sfx = context.createGain();
        const bgm = context.createGain();
        master.gain.value = 0;
        bgm.gain.value = 0;
        sfx.connect(master);
        bgm.connect(master);
        master.connect(context.destination);
        graph = { context, master, sfx, bgm };
      }
      if (graph.context.state === "suspended") void graph.context.resume();
      if (settings) apply(graph, settings);
    },

    /** Remember the latest settings and apply them if the context exists. */
    sync(next: SoundSettings) {
      // Unchanged settings must not restart an in-flight fade.
      if (settings && sameSettings(settings, next)) return;
      settings = next;
      if (graph) apply(graph, next);
    },

    /** Set the SFX level immediately (slider preview runs before the prefs sync). */
    setSfxVolume(volume: number) {
      if (graph) graph.sfx.gain.setValueAtTime(volumeToGain(volume), graph.context.currentTime);
    },

    /** Play one synthesized effect; silent while muted or before unlock. */
    playSfx(name: SfxName) {
      if (!graph || !settings?.soundEnabled || graph.context.state !== "running") return;
      const { context, sfx } = graph;
      const recipe = SFX_RECIPES[name];
      for (const voice of recipe.voices) {
        const start = context.currentTime + voice.delay;
        const end = start + recipe.attack + recipe.release;
        const oscillator = context.createOscillator();
        const envelope = context.createGain();
        oscillator.type = voice.wave;
        oscillator.frequency.setValueAtTime(voice.frequency, start);
        if (voice.endFrequency) oscillator.frequency.exponentialRampToValueAtTime(voice.endFrequency, end);
        envelope.gain.setValueAtTime(0.0001, start);
        envelope.gain.linearRampToValueAtTime(voice.peak, start + recipe.attack);
        envelope.gain.exponentialRampToValueAtTime(0.0001, end);
        oscillator.connect(envelope).connect(sfx);
        oscillator.start(start);
        oscillator.stop(end + 0.02);
        oscillator.onended = () => envelope.disconnect();
      }
    },
  };
}

export type AudioEngine = ReturnType<typeof createAudioEngine>;
