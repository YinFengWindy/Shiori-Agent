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

  it("completes one Day through one atomic bridge command", async () => {
    const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
    const client = createWorldBridgeClient(async (request): Promise<BridgeResponse> => {
      requests.push(request);
      return { id: "response", type: "response", method: request.method, payload: { run_id: "run-day-1" }, error: null };
    });

    await client.completeDay("world-1", "去旧港寻找失踪者。");

    assert.deepEqual(requests, [{
      method: "worlds.days.complete",
      payload: { world_id: "world-1", content: "去旧港寻找失踪者。" },
    }]);
  });

  it("maps dialogue voice synthesis to the MiniMax voice bridge contract", async () => {
    const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
    const invoke = async (request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> => {
      requests.push(request);
      return {
        id: "response",
        type: "response",
        method: request.method,
        payload: { audio_base64: "encoded-mp3", format: "mp3" },
        error: null,
      };
    };

    const result = await createWorldBridgeClient(invoke).synthesizeVoice("你好", {
      voiceId: "voice-1",
      speed: 1.2,
      emotion: "calm",
    });

    assert.deepEqual(result, { audioBase64: "encoded-mp3", format: "mp3" });
    assert.equal(requests.length, 1);
    assert.equal(requests[0].method, "voice.synthesize");
    assert.deepEqual({ ...requests[0].payload, voice_request_id: undefined }, {
      text: "你好",
      voice_id: "voice-1",
      speed: 1.2,
      emotion: "calm",
      voice_request_id: undefined,
    });
    assert.equal(typeof requests[0].payload.voice_request_id, "string");
  });

  it("sends a backend cancellation when the voice signal is aborted", async () => {
    const controller = new AbortController();
    let resolveSynthesis!: (response: BridgeResponse) => void;
    const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
    const invoke = async (request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse> => {
      requests.push(request);
      if (request.method === "voice.synthesize") {
        return await new Promise<BridgeResponse>((resolve) => { resolveSynthesis = resolve; });
      }
      return { id: "cancel", type: "response", method: request.method, payload: { cancelled: true }, error: null };
    };
    const synthesis = createWorldBridgeClient(invoke).synthesizeVoice("你好", { voiceId: "voice-1", speed: 1 }, controller.signal);
    await new Promise<void>((resolve) => setImmediate(resolve));
    controller.abort();
    await new Promise<void>((resolve) => setImmediate(resolve));
    assert.equal(requests[1].method, "voice.synthesize.cancel");
    assert.equal(requests[1].payload.voice_request_id, requests[0].payload.voice_request_id);
    resolveSynthesis({ id: "response", type: "response", method: "voice.synthesize", payload: {}, error: { code: "cancelled", message: "已取消" } });
    await assert.rejects(synthesis);
  });
});
