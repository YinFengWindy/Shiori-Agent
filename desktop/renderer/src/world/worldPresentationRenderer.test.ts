import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { PerformancePlan, PresentationCue } from "./presentationProtocol";
import {
  createWorldAssetManifest,
  playPresentationPlan,
  TextWorldPresentationRenderer,
  type WorldPresentationRenderer,
} from "./worldPresentationRenderer";

function cue(sequence: number, kind: PresentationCue["kind"], payload: Record<string, unknown>): PresentationCue {
  return {
    schemaVersion: 1,
    cueId: `cue-${sequence}`,
    planId: "plan-1",
    sequence,
    kind,
    payload,
    parallelGroup: null,
    blocking: kind === "dialogue",
    completionState: "completed",
    skipState: "skipped",
    checkpoint: kind === "dialogue",
  };
}

function plan(cues: PresentationCue[]): PerformancePlan {
  return { schemaVersion: 1, planId: "plan-1", worldId: "world-1", eventId: "event-1", sourceSequence: 1, cues };
}

describe("worldPresentationRenderer", () => {
  it("plays cues in order and checkpoints only after rendering", async () => {
    const events: string[] = [];
    const renderer: WorldPresentationRenderer = {
      kind: "pixi",
      initialize: async () => undefined,
      prepare: async () => { events.push("prepare"); },
      recover: async () => undefined,
      render: async (item) => { events.push(`render:${item.cueId}`); },
      pause: () => undefined,
      resume: () => undefined,
      skip: () => undefined,
      dispose: () => undefined,
    };
    const value = plan([cue(0, "background", {}), cue(1, "dialogue", { content: "到了。" })]);
    await playPresentationPlan(renderer, { plan: value, manifest: [], fallbackText: "fallback" }, {
      onCueComplete: (item) => { events.push(`checkpoint:${item.cueId}`); },
    });
    assert.deepEqual(events, ["prepare", "render:cue-0", "render:cue-1", "checkpoint:cue-1"]);
  });

  it("reconstructs completed visuals without repeating their checkpoints", async () => {
    const rendered: string[] = [];
    const recovered: string[] = [];
    const renderer: WorldPresentationRenderer = {
      kind: "pixi",
      initialize: async () => undefined,
      prepare: async () => undefined,
      recover: async (items) => { recovered.push(...items.map((item) => item.cueId)); },
      render: async (item) => { rendered.push(item.cueId); },
      pause: () => undefined,
      resume: () => undefined,
      skip: () => undefined,
      dispose: () => undefined,
    };
    const value = plan([
      cue(0, "background", {}),
      cue(1, "sprites", {}),
      cue(2, "dialogue", { content: "继续。" }),
    ]);

    await playPresentationPlan(
      renderer,
      { plan: value, manifest: [], fallbackText: "fallback" },
      { startCueIndex: 2 },
    );

    assert.deepEqual(recovered, ["cue-0", "cue-1"]);
    assert.deepEqual(rendered, ["cue-2"]);
  });

  it("keeps the latest readable dialogue in the text adapter", async () => {
    const snapshots: string[] = [];
    const renderer = new TextWorldPresentationRenderer((snapshot) => snapshots.push(snapshot.text));
    await renderer.prepare({ plan: plan([]), manifest: [], fallbackText: "事件继续。" });
    await renderer.render(cue(0, "dialogue", { content: "你终于来了。" }));
    await renderer.render(cue(1, "camera", { kind: "pan" }));
    assert.deepEqual(snapshots, ["事件继续。", "你终于来了。"]) ;
    assert.equal(renderer.snapshot().cueId, "cue-0");
  });

  it("builds a manifest only from explicit controlled asset references", () => {
    const value = plan([
      cue(0, "background", { asset: "harbor", assetUrl: "shiori-asset://local/harbor-token" }),
      cue(1, "sprites", { items: [{ actorId: "oc-1", assetId: "mood-alert", imageUrl: "shiori-asset://local/mood-token", fallbackIds: ["avatar-1"] }] }),
      cue(2, "cg", { tasks: [{ assetId: "remote", url: "https://example.com/cg.png" }] }),
    ]);
    assert.deepEqual(createWorldAssetManifest(value), [
      { id: "harbor", url: "shiori-asset://local/harbor-token", kind: "background", fallbackIds: undefined },
      { id: "mood-alert", url: "shiori-asset://local/mood-token", kind: "character", fallbackIds: ["avatar-1"] },
    ]);
  });
});
