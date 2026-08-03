/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { BridgeResponse } from "../../../src/shared";
import { createStoryBridgeClient } from "./storyBridgeClient";
import { StoryBridgeError } from "./types";

function storyPayload(revision = 4, operation: "awaiting_player" | "generating" = "awaiting_player") {
  return {
    id: "story-1",
    title: "雨港",
    background: "潮汐带回名字",
    status: "active" as const,
    revision,
    roleSnapshot: { id: "role-1", name: "澪" },
    playerProfile: { display_name: "岚", appearance: "短发", identity: "抄写员" },
    segment: { id: "segment-1", sequence: 1, startsAt: "2026-08-02T10:00:00+08:00", status: "active", mode: "plot", operation, openingContext: {}, runtimeSnapshot: {} },
    beats: [{ id: "beat-1", storyId: "story-1", segmentId: "segment-1", turnId: "turn-1", sequence: 1, effectiveAt: "2026-08-02T10:00:00+08:00", text: "风从走廊尽头吹来。", kind: "narration" as const, speaker: null, recordedAt: "2026-08-02T10:00:00+08:00" }],
    cues: [],
    turns: [],
  };
}

describe("createStoryBridgeClient", () => {
  it("calls stories.list and maps catalog fields directly", async () => {
    const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
    const invoke = async (request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> => {
      requests.push(request);
      return { id: "response", type: "response", method: request.method, payload: { stories: [{ story_id: "story-1", relative_db_path: "story-1/story.db", title: "雨港", status: "active", created_at: "2026-08-02T10:00:00+08:00" }] }, error: null };
    };

    assert.deepEqual(await createStoryBridgeClient(invoke).listStories(), [{ storyId: "story-1", relativeDbPath: "story-1/story.db", title: "雨港", status: "active", createdAt: "2026-08-02T10:00:00+08:00" }]);
    assert.deepEqual(requests, [{ method: "stories.list", payload: {} }]);
  });

  it("returns the repository Story read model without a compatibility projection", async () => {
    const story = storyPayload();
    const client = createStoryBridgeClient(async (request): Promise<BridgeResponse> => ({ id: "response", type: "response", method: request.method, payload: { story }, error: null }));
    const result = await client.getStory("story-1");
    assert.equal(result.title, "雨港");
    assert.equal(result.beats[0].text, "风从走廊尽头吹来。");
    assert.equal(result.segment.operation, "awaiting_player");
  });

  it("creates a Story with one selected role and China time", async () => {
    const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
    const client = createStoryBridgeClient(async (request): Promise<BridgeResponse> => {
      requests.push(request);
      return { id: "response", type: "response", method: request.method, payload: { story: storyPayload(0, "generating") }, error: null };
    });
    await client.createStory({ title: "雨港", background: "潮汐", startsAt: "2026-08-02T10:00", roleId: "role-1", playerProfile: { displayName: "岚", appearance: "短发", identity: "抄写员" } });
    assert.deepEqual(requests[0], { method: "stories.create", payload: { title: "雨港", background: "潮汐", starts_at: "2026-08-02T10:00:00+08:00", role_id: "role-1", player_profile: { display_name: "岚", appearance: "短发", identity: "抄写员" } } });
  });

  it("submits player input with the latest Story revision", async () => {
    const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
    const client = createStoryBridgeClient(async (request): Promise<BridgeResponse> => {
      requests.push(request);
      return { id: "response", type: "response", method: request.method, payload: { story: storyPayload(request.method === "stories.get" ? 4 : 5, "generating") }, error: null };
    });
    await client.getStory("story-1");
    await client.submitInput("story-1", "推开门。");
    assert.deepEqual(requests[1], { method: "stories.input", payload: { story_id: "story-1", input: "推开门。", expected_revision: 4 } });
  });

  it("surfaces bridge failures as stable Story errors", async () => {
    const invoke = async (request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> => ({ id: "response", type: "response", method: request.method, payload: {}, error: { code: "story_conflict", message: "剧情版本已变化" } });
    await assert.rejects(() => createStoryBridgeClient(invoke).continueStory("story-1"), (error: unknown) => error instanceof StoryBridgeError && error.code === "story_conflict");
  });
});
