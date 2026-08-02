/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { BridgeResponse } from "../../../src/shared";
import { createStoryBridgeClient } from "./bridgeClient";

describe("createStoryBridgeClient", () => {
  it("maps a player-authored opening to the Story bridge contract", async () => {
    const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
    const invoke = async (request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> => {
      requests.push(request);
      return { id: "response", type: "response", method: request.method, payload: { story: { id: "story-1" } }, error: null };
    };

    await createStoryBridgeClient(invoke).createStory({
      title: "夏日来信",
      background: "午后的旧校舍",
      startsAt: "2026-08-01T09:00:00+08:00",
      roleId: "role-1",
      playerProfile: { displayName: "悠", appearance: "短发", identity: "转学生" },
    });

    assert.deepEqual(requests, [{
      method: "stories.create",
      payload: {
        title: "夏日来信",
        background: "午后的旧校舍",
        starts_at: "2026-08-01T09:00:00+08:00",
        role_id: "role-1",
        player_profile: { display_name: "悠", appearance: "短发", identity: "转学生" },
      },
    }]);
  });

  it("includes the rendered revision when submitting the next turn", async () => {
    const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
    const invoke = async (request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> => {
      requests.push(request);
      return { id: "response", type: "response", method: request.method, payload: {}, error: null };
    };

    await createStoryBridgeClient(invoke).submitInput("story-1", "推开门", 4);

    assert.deepEqual(requests, [{
      method: "stories.input",
      payload: { story_id: "story-1", input: "推开门", expected_revision: 4 },
    }]);
  });
});
