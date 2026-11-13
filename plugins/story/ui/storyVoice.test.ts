import assert from "node:assert/strict";
import { test } from "node:test";
import type { PluginServiceReference } from "@yinfengwindy/shiori-sdk";
import { createStoryVoiceSource } from "./storyVoice";
import { createStoryDetails } from "./testFixtures";
import type { StoryVoice, StoryVoiceAudio } from "./types";

const fish: PluginServiceReference = { plugin_id: "fish_audio", service_id: "tts" };
const sovits: PluginServiceReference = { plugin_id: "gpt_sovits_tts", service_id: "tts" };
const line = { beatId: "beat-1", fragmentIndex: 0, text: "你终于来了。" };

function harness(saved: Array<StoryVoice & StoryVoiceAudio>) {
  const synthesized: Array<{ provider: PluginServiceReference; payload: Record<string, unknown> | undefined }> = [];
  const savedCalls: Array<{ provider: PluginServiceReference; audio: StoryVoiceAudio }> = [];
  let releaseSynthesis: () => void = () => undefined;
  const synthesisGate = new Promise<void>((resolve) => { releaseSynthesis = resolve; });
  const source = createStoryVoiceSource({
    rpc: {
      services: {
        list: async () => ({ services: [] }),
        call: async <T,>(provider: PluginServiceReference, _name: string, payload?: Record<string, unknown>) => {
          synthesized.push({ provider, payload });
          await synthesisGate;
          return { audio_base64: "c3ludGg=", format: "mp3" } as T;
        },
      },
    },
    stories: {
      getVoice: async (_storyId, beatId, fragmentIndex) => saved.find((voice) => voice.beatId === beatId && voice.fragmentIndex === fragmentIndex) ?? null,
      saveVoice: async (_storyId, beatId, fragmentIndex, provider, audio) => {
        savedCalls.push({ provider, audio });
        return { beatId, fragmentIndex, provider, format: audio.format };
      },
    },
    onSaveError: (cause) => { throw cause; },
  });
  return { source, synthesized, savedCalls, releaseSynthesis };
}

test("a line saved by the same provider replays from the Story save without a new synthesis", async () => {
  const stored = { beatId: "beat-1", fragmentIndex: 0, provider: fish, format: "wav" as const, audio_base64: "c2F2ZWQ=" };
  const story = createStoryDetails({ voices: [{ beatId: "beat-1", fragmentIndex: 0, provider: fish, format: "wav" }] });
  const { source, synthesized } = harness([stored]);

  assert.deepEqual(await source.load(story, line, fish), { audio_base64: "c2F2ZWQ=", format: "wav" });
  assert.equal(synthesized.length, 0);
});

test("switching provider synthesizes once in the role's voice and saves the new line", async () => {
  const stored = { beatId: "beat-1", fragmentIndex: 0, provider: fish, format: "wav" as const, audio_base64: "c2F2ZWQ=" };
  const story = createStoryDetails({ voices: [{ beatId: "beat-1", fragmentIndex: 0, provider: fish, format: "wav" }] });
  const { source, synthesized, savedCalls, releaseSynthesis } = harness([stored]);

  const first = source.load(story, line, sovits);
  const concurrent = source.load(story, line, sovits);
  releaseSynthesis();
  assert.deepEqual(await first, { audio_base64: "c3ludGg=", format: "mp3" });
  assert.deepEqual(await concurrent, await first);
  assert.equal(synthesized.length, 1);
  assert.deepEqual(synthesized[0], { provider: sovits, payload: { text: "你终于来了。", role_id: "role-1", mood: "" } });
  assert.deepEqual(savedCalls, [{ provider: sovits, audio: { audio_base64: "c3ludGg=", format: "mp3" } }]);

  // Played again later in the session: served from memory, no second request.
  await source.load(story, line, sovits);
  assert.equal(synthesized.length, 1);
});
