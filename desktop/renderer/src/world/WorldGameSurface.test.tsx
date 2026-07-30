/// <reference types="node" />

import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it } from "node:test";
import { WorldGameSurface } from "./WorldGameSurface";
import { createWorldDetails } from "./testFixtures";
import { selectWorldGamePresentation } from "./worldGamePresentation";

function render(world = createWorldDetails()) {
  return renderToStaticMarkup(
    <WorldGameSurface
      world={world}
      onOpenTimeline={() => undefined}
      onExitWorkspace={() => undefined}
      onSubmitAction={async () => true}
      onAdvance={() => undefined}
      onResolveBarrier={() => undefined}
      onRedrawShot={() => undefined}
      onPause={() => undefined}
      onResume={() => undefined}
      onCheckpoint={() => undefined}
    />,
  );
}

describe("WorldGameSurface", () => {
  it("renders the stage and performance controls for a queued plan", () => {
    const base = createWorldDetails();
    const markup = render({
      ...base,
      presentation: {
        session: {
          worldId: base.id,
          lastPresentedEventSequence: 0,
          activePlanId: null,
          activeCueIndex: 0,
          status: "playing",
          updatedAt: "2026-07-30T00:00:00+00:00",
        },
        plans: [{
          schemaVersion: 1,
          planId: "plan-1",
          worldId: base.id,
          eventId: base.scene.beats[0].id,
          sourceSequence: 1,
          cues: [{
            schemaVersion: 1,
            cueId: "cue-1",
            planId: "plan-1",
            sequence: 0,
            kind: "dialogue",
            payload: { content: base.scene.beats[0].content },
            parallelGroup: null,
            blocking: true,
            completionState: "completed",
            skipState: "skipped",
            checkpoint: true,
          }],
        }],
      },
    });

    assert.match(markup, /data-testid="world-game-surface"/);
    assert.match(markup, /data-testid="world-stage"/);
    assert.match(markup, /aria-label="暂停演出"/);
    assert.match(markup, /aria-label="跳过当前演出"/);
    assert.match(markup, /aria-label="打开演出菜单"/);
    assert.match(markup, />你终于来了。</);
    assert.doesNotMatch(markup, /aria-label="提交行动"/);
  });

  it("shows action input after the presentation queue is empty", () => {
    const markup = render(createWorldDetails({ presentation: undefined }));

    assert.doesNotMatch(markup, /data-testid="world-stage"/);
    assert.match(markup, /aria-label="提交行动"/);
    assert.match(markup, /岚准备怎么做？/);
  });

  it("shows a decision barrier instead of the action composer", () => {
    const base = createWorldDetails({ status: "barrier" });
    const markup = render({
      ...base,
      scene: {
        ...base.scene,
        barriers: [{ id: "barrier-1", title: "钟声之后", context: "必须决定是否开门", affectedOcNames: ["岚"], choices: [{ id: "open", label: "打开门" }] }],
      },
    });

    assert.match(markup, /aria-label="待决事件"/);
    assert.match(markup, />打开门</);
    assert.doesNotMatch(markup, /aria-label="提交行动"/);
  });

  it("does not start a stale plan while the world is awaiting a barrier", () => {
    const base = createWorldDetails({ status: "barrier" });
    const world = {
      ...base,
      scene: {
        ...base.scene,
        barriers: [{ id: "barrier-1", title: "钟声之后", context: "必须决定是否开门", affectedOcNames: ["岚"], choices: [{ id: "open", label: "打开门" }] }],
      },
      presentation: {
        session: {
          worldId: base.id,
          lastPresentedEventSequence: 1,
          activePlanId: null,
          activeCueIndex: 0,
          status: "awaiting_barrier" as const,
          updatedAt: "2026-07-30T00:00:00+00:00",
        },
        plans: [{
          schemaVersion: 1 as const,
          planId: "stale-plan",
          worldId: base.id,
          eventId: base.scene.beats[0].id,
          sourceSequence: 2,
          cues: [],
        }],
      },
    };
    const selection = selectWorldGamePresentation(world);
    assert.equal(selection.plan, null);
    assert.equal(selection.canPlay, false);
  });

  it("selects the active plan and restores its cue cursor", () => {
    const base = createWorldDetails();
    const plans = [
      { planId: "plan-1", eventId: "beat-1", sourceSequence: 1 },
      { planId: "plan-2", eventId: "beat-2", sourceSequence: 2 },
    ].map(({ planId, eventId, sourceSequence }) => ({
      schemaVersion: 1 as const,
      planId,
      worldId: base.id,
      eventId,
      sourceSequence,
      cues: [{
        schemaVersion: 1 as const,
        cueId: `${planId}-cue`,
        planId,
        sequence: 0,
        kind: "dialogue" as const,
        payload: { content: "继续。" },
        parallelGroup: null,
        blocking: true,
        completionState: "completed",
        skipState: "skipped",
        checkpoint: true,
      }],
    }));
    const world = {
      ...base,
      scene: { ...base.scene, beats: [...base.scene.beats, { ...base.scene.beats[0], id: "beat-2", content: "第二段。" }] },
      presentation: {
        session: {
          worldId: base.id,
          lastPresentedEventSequence: 1,
          activePlanId: "plan-2",
          activeCueIndex: 1,
          status: "playing" as const,
          updatedAt: "2026-07-30T00:00:00+00:00",
        },
        plans,
      },
    };
    const selection = selectWorldGamePresentation(world);
    assert.equal(selection.plan?.planId, "plan-2");
    assert.equal(selection.preloadPlan, undefined);
    assert.equal(selection.startCueIndex, 1);
    assert.equal(selection.beat?.id, "beat-2");
  });
});
