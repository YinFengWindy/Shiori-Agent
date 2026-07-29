/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { BridgeResponse } from "../../../src/shared";
import { createWorldBridgeClient } from "./bridgeClient";
import { WorldBridgeError } from "./types";

describe("createWorldBridgeClient", () => {
  it("maps semantic world loading to the expected bridge request", async () => {
    const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
    const invoke = async (request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> => {
      requests.push(request);
      return { id: "response", type: "response", method: request.method, payload: { worlds: [] }, error: null };
    };
    const worlds = await createWorldBridgeClient(invoke).listWorlds();
    assert.deepEqual(worlds, []);
    assert.deepEqual(requests, [{ method: "worlds.list", payload: {} }]);
  });

  it("lets bridge failures surface as stable domain errors", async () => {
    const invoke = async (request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> => ({ id: "response", type: "response", method: request.method, payload: {}, error: { code: "world_conflict", message: "既定事实发生冲突" } });
    await assert.rejects(() => createWorldBridgeClient(invoke).advance("world-1"), (error: unknown) => error instanceof WorldBridgeError && error.code === "world_conflict");
  });

  it("maps presentation checkpoints to the durable session bridge", async () => {
    const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
    const invoke = async (request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> => {
      requests.push(request);
      return {
        id: "response",
        type: "response",
        method: request.method,
        payload: {
          presentation: {
            session: {
              worldId: "world-1",
              lastPresentedEventSequence: 1,
              activePlanId: null,
              activeCueIndex: 0,
              status: "awaiting_action",
              updatedAt: "2026-07-29T00:00:00+00:00",
            },
            plans: [],
          },
        },
        error: null,
      };
    };

    const state = await createWorldBridgeClient(invoke).checkpointPresentation("world-1", "plan-1", 0);
    assert.equal(state.session.lastPresentedEventSequence, 1);
    assert.deepEqual(requests, [{
      method: "worlds.presentation.checkpoint",
      payload: { world_id: "world-1", plan_id: "plan-1", cue_index: 0 },
    }]);
  });
});
