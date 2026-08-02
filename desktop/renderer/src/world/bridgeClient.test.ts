/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { BridgeResponse } from "../../../src/shared";
import { createWorldBridgeClient } from "./bridgeClient";
import { WorldBridgeError } from "./types";

describe("createWorldBridgeClient", () => {
  it("maps the retained workspace list to stories.list", async () => {
    const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
    const invoke = async (request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> => {
      requests.push(request);
      return { id: "response", type: "response", method: request.method, payload: { stories: [] }, error: null };
    };

    assert.deepEqual(await createWorldBridgeClient(invoke).listWorlds(), []);
    assert.deepEqual(requests, [{ method: "stories.list", payload: {} }]);
  });

  it("adapts a committed Story into the existing day-surface model", async () => {
    const client = createWorldBridgeClient(async (request): Promise<BridgeResponse> => ({
      id: "response",
      type: "response",
      method: request.method,
      payload: { story: {
        id: "story-1", title: "雨港", background: "潮汐带回名字", status: "active", revision: 4,
        roleSnapshot: { id: "role-1", name: "澪" },
        playerProfile: { display_name: "岚", appearance: "短发", identity: "抄写员" },
        segment: { startsAt: "2026-08-02T10:00:00+08:00", operation: "awaiting_player" },
        beats: [{ id: "beat-1", sequence: 1, effective_at: "2026-08-02T10:00:00+08:00", text: "风从走廊尽头吹来。", kind: "narration", speaker: null }],
      } }, error: null,
    }));

    const story = await client.getWorld("story-1");
    assert.equal(story.name, "雨港");
    assert.equal(story.days[0].events[0].content, "风从走廊尽头吹来。");
    assert.equal(story.scene.actionPrompt, "写下你的行动或回应...");
  });

  it("creates a Story with one selected role and China time", async () => {
    const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
    const client = createWorldBridgeClient(async (request): Promise<BridgeResponse> => {
      requests.push(request);
      return { id: "response", type: "response", method: request.method, payload: { story: {
        id: "story-1", title: "雨港", background: "潮汐", status: "active", revision: 0,
        roleSnapshot: {}, playerProfile: {}, segment: { startsAt: "2026-08-02T10:00:00+08:00", operation: "generating" }, beats: [],
      } }, error: null };
    });

    const draft = await client.previewDraft({ name: "雨港", premise: "潮汐", rules: "", tone: "", seed: "seed", selectedRoleIds: ["role-1"], firstOc: { name: "岚", identity: "抄写员", entryTime: "2026-08-02T10:00", entryLocation: "短发", primaryGoal: "" } });
    await client.confirmDraft(draft.id, draft.nativeIdentities);

    assert.deepEqual(requests[0], { method: "stories.create", payload: {
      title: "雨港", background: "潮汐", starts_at: "2026-08-02T10:00:00+08:00", role_id: "role-1",
      player_profile: { display_name: "岚", appearance: "短发", identity: "抄写员" },
    } });
  });

  it("submits player input with the Story revision", async () => {
    const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
    const client = createWorldBridgeClient(async (request): Promise<BridgeResponse> => {
      requests.push(request);
      return { id: "response", type: "response", method: request.method, payload: { story: {
        id: "story-1", title: "雨港", background: "潮汐", status: "active", revision: request.method === "stories.get" ? 4 : 5,
        roleSnapshot: {}, playerProfile: {}, segment: { startsAt: "2026-08-02T10:00:00+08:00", operation: "generating" }, beats: [],
      } }, error: null };
    });
    await client.getWorld("story-1");
    await client.completeDay("story-1", "推开门。");
    assert.deepEqual(requests[1], { method: "stories.input", payload: { story_id: "story-1", input: "推开门。", expected_revision: 4 } });
  });

  it("lets Story bridge failures surface as stable domain errors", async () => {
    const invoke = async (request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> => ({ id: "response", type: "response", method: request.method, payload: {}, error: { code: "story_conflict", message: "剧情版本已变化" } });
    await assert.rejects(() => createWorldBridgeClient(invoke).advance("story-1"), (error: unknown) => error instanceof WorldBridgeError && error.code === "story_conflict");
  });
});
