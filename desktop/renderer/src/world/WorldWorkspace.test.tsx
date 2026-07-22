/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { WorldWorkspace } from "./WorldWorkspace";
import { createWorldDetails, createWorldSummary } from "./testFixtures";

function render(world = createWorldDetails()) {
  return renderToStaticMarkup(<WorldWorkspace worlds={[createWorldSummary(world)]} world={world} onSelectWorld={() => undefined} onSwitchOc={() => undefined} onCreateWorld={() => undefined} onOpenTimeline={() => undefined} onOpenFocus={() => undefined} onSubmitAction={async () => true} onAdvance={() => undefined} onResolveBarrier={() => undefined} onCancel={() => undefined} onRedrawShot={() => undefined} />);
}

describe("WorldWorkspace", () => {
  it("renders the world, shared scene, OC switcher, and status in three columns", () => {
    const markup = render();
    assert.match(markup, /data-testid="world-workspace"/);
    assert.match(markup, />雨港</);
    assert.match(markup, />灯塔下</);
    assert.match(markup, />当前 OC</);
    assert.match(markup, /aria-label="提交行动"/);
  });

  it("replaces the action composer with the first shared decision barrier", () => {
    const base = createWorldDetails();
    const markup = render(createWorldDetails({ status: "barrier", scene: { ...base.scene, barriers: [{ id: "barrier-1", title: "钟声之后", context: "必须决定是否开门", affectedOcNames: ["岚"], choices: [{ id: "open", label: "打开门" }] }] } }));
    assert.match(markup, />钟声之后</);
    assert.match(markup, />打开门</);
    assert.doesNotMatch(markup, /aria-label="提交行动"/);
  });

  it("does not expose transport identifiers or sequence labels", () => {
    const markup = render();
    assert.doesNotMatch(markup, />world-1</);
    assert.doesNotMatch(markup, />oc-1</);
    assert.doesNotMatch(markup, /run[_ ]?id/i);
    assert.doesNotMatch(markup, /event sequence/i);
  });
});
