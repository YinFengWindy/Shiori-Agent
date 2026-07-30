/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { PerformancePlan, PresentationCue } from "./presentationProtocol";
import {
  createWorldStagePlaybackCoordinator,
  type WorldStagePlaybackCoordinatorOptions,
} from "./WorldStage";
import type {
  WorldPresentationPrepareRequest,
  WorldPresentationRenderer,
} from "./worldPresentationRenderer";

function cue(sequence: number): PresentationCue {
  return {
    schemaVersion: 1,
    cueId: `cue-${sequence}`,
    planId: "plan-1",
    sequence,
    kind: "dialogue",
    payload: { content: `内容 ${sequence}` },
    parallelGroup: null,
    blocking: true,
    completionState: "completed",
    skipState: "skipped",
    checkpoint: true,
  };
}

function request(): WorldPresentationPrepareRequest {
  const plan: PerformancePlan = {
    schemaVersion: 1,
    planId: "plan-1",
    worldId: "world-1",
    eventId: "event-1",
    sourceSequence: 1,
    cues: [cue(0), cue(1), cue(2)],
  };
  return { plan, manifest: [], fallbackText: "fallback" };
}

function renderer(
  kind: WorldPresentationRenderer["kind"],
  events: string[],
  failCueId?: string,
): WorldPresentationRenderer {
  return {
    kind,
    initialize: async () => undefined,
    prepare: async () => { events.push(`${kind}:prepare`); },
    recover: async (items) => { events.push(`${kind}:recover:${items.map((item) => item.cueId).join(",")}`); },
    render: async (item) => {
      events.push(`${kind}:render:${item.cueId}`);
      if (item.cueId === failCueId) throw new Error(`${kind} render failed`);
    },
    pause: () => undefined,
    resume: () => undefined,
    skip: () => undefined,
    dispose: () => undefined,
  };
}

function coordinatorOptions(
  overrides: Partial<WorldStagePlaybackCoordinatorOptions> = {},
): WorldStagePlaybackCoordinatorOptions {
  const events: string[] = [];
  return {
    request: request(),
    startCueIndex: 0,
    signal: new AbortController().signal,
    pixiRenderer: renderer("pixi", events),
    textRenderer: renderer("text", events),
    onFallback: () => { events.push("fallback"); },
    ...overrides,
  };
}

describe("WorldStage playback coordinator", () => {
  it("keeps startCueIndex when a renderer failure activates text fallback", async () => {
    const events: string[] = [];
    const options = coordinatorOptions({
      pixiRenderer: renderer("pixi", events, "cue-1"),
      textRenderer: renderer("text", events),
      startCueIndex: 1,
      onFallback: () => { events.push("fallback"); },
    });
    const checkpoints: string[] = [];
    const coordinator = createWorldStagePlaybackCoordinator({
      ...options,
      onCueComplete: async (item) => { checkpoints.push(item.cueId); },
    });

    assert.equal(await coordinator.playPixi(), "text");
    assert.deepEqual(events, [
      "pixi:prepare",
      "pixi:recover:cue-0",
      "pixi:render:cue-1",
      "fallback",
      "text:prepare",
      "text:recover:cue-0",
      "text:render:cue-1",
      "text:render:cue-2",
    ]);
    assert.deepEqual(checkpoints, ["cue-1", "cue-2"]);
  });

  it("does not checkpoint a cue twice when Pixi falls back after a completed cue", async () => {
    const events: string[] = [];
    const options = coordinatorOptions({
      pixiRenderer: renderer("pixi", events, "cue-1"),
      textRenderer: renderer("text", events),
      onFallback: () => { events.push("fallback"); },
    });
    const checkpoints: string[] = [];
    const coordinator = createWorldStagePlaybackCoordinator({
      ...options,
      onCueComplete: async (item) => { checkpoints.push(item.cueId); },
    });

    assert.equal(await coordinator.playPixi(), "text");
    assert.deepEqual(checkpoints, ["cue-0", "cue-1", "cue-2"]);
  });

  it("does not activate text fallback when checkpoint persistence fails", async () => {
    const events: string[] = [];
    const options = coordinatorOptions({
      pixiRenderer: renderer("pixi", events),
      textRenderer: renderer("text", events),
      onFallback: () => { events.push("fallback"); },
    });
    const coordinator = createWorldStagePlaybackCoordinator({
      ...options,
      onCueComplete: async () => { throw new Error("bridge checkpoint failed"); },
    });

    await assert.rejects(() => coordinator.playPixi(), /bridge checkpoint failed/);
    assert.equal(events.includes("fallback"), false);
    assert.equal(events.some((event) => event.startsWith("text:")), false);
  });
});
