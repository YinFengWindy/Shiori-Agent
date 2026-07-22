/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { WorldTimelineView } from "./WorldTimelineView";

const entries = [{ id: "anchor-1", timeLabel: "第一日", title: "潮水退去", summary: "旧港露出了石阶。", visibility: "known" as const, involvedNames: ["澪"], canCopy: true, canEnter: true }];

describe("WorldTimelineView", () => {
  it("renders a full history with cognitive and omniscient controls", () => {
    const markup = renderToStaticMarkup(<WorldTimelineView worldName="雨港" activeOcName="岚" entries={entries} perspective="known" onBack={() => undefined} onPerspectiveChange={() => undefined} onCopyWorld={() => undefined} onPreviewBackfill={() => undefined} onCommitBackfill={() => undefined} />);
    assert.match(markup, /data-testid="world-timeline-view"/);
    assert.match(markup, />认知</);
    assert.match(markup, />全知</);
    assert.match(markup, />从这里加入 OC</);
    assert.match(markup, />创建世界副本</);
  });

  it("shows causal conflicts without offering an invalid commit", () => {
    const markup = renderToStaticMarkup(<WorldTimelineView worldName="雨港" activeOcName="岚" entries={entries} perspective="omniscient" backfillPreview={{ anchorId: "anchor-1", oc: { name: "弥", identity: "医师", entryTime: "第一日", entryLocation: "旧港", primaryGoal: "救人" }, stages: [], conflicts: ["该行动会覆盖既定的港口封锁"], allowed: false }} onBack={() => undefined} onPerspectiveChange={() => undefined} onCopyWorld={() => undefined} onPreviewBackfill={() => undefined} onCommitBackfill={() => undefined} />);
    assert.doesNotMatch(markup, />确认加入世界</);
    assert.match(markup, />全知</);
  });
});
