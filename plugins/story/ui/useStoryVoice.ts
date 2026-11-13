import { useEffect, useState } from "react";
import { useLatestRef, type PluginServiceReference } from "@yinfengwindy/shiori-sdk";
import { describeStoryFailure } from "./storyFailure";
import { StoryVoicePlayer, type StoryVoiceLine, type StoryVoiceSource } from "./storyVoice";
import type { StoryDetails } from "./types";

type StoryFailure = ReturnType<typeof describeStoryFailure>;

type UseStoryVoiceOptions = {
  source: StoryVoiceSource | undefined;
  story: StoryDetails;
  provider: PluginServiceReference | null;
  volume: number;
  /** The dialogue fragment on screen, or null for narration and generation states. */
  line: StoryVoiceLine | null;
  /** The next dialogue fragment, synthesized ahead so it plays without a wait. */
  nextLine: StoryVoiceLine | null;
};

/** State of the voice line for the fragment on screen. */
export type StoryVoiceState = {
  /** True while the current line is loading or playing; auto-play waits for it. */
  speaking: boolean;
  failure: StoryFailure | null;
};

function voiceKey(storyId: string, line: StoryVoiceLine | null, provider: PluginServiceReference | null) {
  return line && provider ? `${storyId}:${line.beatId}:${line.fragmentIndex}:${provider.plugin_id}/${provider.service_id}` : "";
}

/**
 * Voices each dialogue fragment as it is presented: one line plays at a time,
 * the next is prepared ahead, and leaving a line stops it at once.
 */
export function useStoryVoice({ source, story, provider, volume, line, nextLine }: UseStoryVoiceOptions): StoryVoiceState {
  const [player] = useState(() => new StoryVoicePlayer());
  const [settled, setSettled] = useState<{ key: string; failure: StoryFailure | null } | null>(null);
  const key = source ? voiceKey(story.id, line, provider) : "";
  const nextKey = source ? voiceKey(story.id, nextLine, provider) : "";
  // Read when a line starts: a fresh read model of the same Story must not restart the line.
  const latest = useLatestRef({ story, provider, line, nextLine });

  useEffect(() => () => player.dispose(), [player]);
  useEffect(() => player.setVolume(volume), [player, volume]);

  useEffect(() => {
    const { story: current, provider: currentProvider, line: currentLine } = latest.current;
    if (!key || !source || !currentProvider || !currentLine) return;
    const controller = new AbortController();
    void source.load(current, currentLine, currentProvider)
      .then((audio) => controller.signal.aborted ? undefined : player.play(audio, controller.signal))
      .then(() => { if (!controller.signal.aborted) setSettled({ key, failure: null }); })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setSettled({ key, failure: describeStoryFailure(cause, "语音生成失败") }); });
    return () => {
      controller.abort();
      player.stop();
    };
  }, [key, latest, player, source]);

  useEffect(() => {
    const { story: current, provider: currentProvider, nextLine: upcoming } = latest.current;
    if (!nextKey || !source || !currentProvider || !upcoming) return;
    // A failed prefetch is not kept: the line loads again when it becomes current and reports there.
    source.load(current, upcoming, currentProvider).catch(() => undefined);
  }, [latest, nextKey, source]);

  const done = settled?.key === key;
  return {
    speaking: Boolean(key) && !done,
    failure: done ? settled.failure : null,
  };
}
