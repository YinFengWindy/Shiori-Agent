/// <reference types="node" />

import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it } from "node:test";
import { createSceneBeat, createWorldDetails } from "./testFixtures";
import { WorldDaySurface } from "./WorldDaySurface";

function render(overrides: Parameters<typeof createWorldDetails>[0] = {}) {
  return renderToStaticMarkup(
    <WorldDaySurface
      world={createWorldDetails(overrides)}
      busy={false}
      error=""
      onCompleteDay={async () => true}
      onOpenSettings={() => undefined}
      onExit={() => undefined}
    />,
  );
}

describe("WorldDaySurface", () => {
  it("renders a plot-first day chronicle without attributes or workspace columns", () => {
    const markup = render();

    assert.match(markup, /data-testid="world-day-surface"/);
    assert.match(markup, />Day 3</);
    assert.match(markup, /你终于来了。/);
    assert.match(markup, /aria-label="提交剧情行动"/);
    assert.match(markup, /data-current-day="true"/);
    assert.match(markup, /aria-label="剧情设置"/);
    assert.match(markup, /aria-label="返回剧情列表"/);
    assert.doesNotMatch(markup, /属性|好感度|world-workspace/);
  });

  it("keeps story metadata out of a persistent top bar", () => {
    const markup = render({ name: "回家的诱惑", premise: "深夜归家的开场。" });

    assert.doesNotMatch(markup, />回家的诱惑</);
    assert.doesNotMatch(markup, />深夜归家的开场。</);
    assert.doesNotMatch(markup, /<header/);
  });

  it("keeps committed beats visible in chronological order", () => {
    const markup = render({
      days: [
        { dayIndex: 2, title: "Day 2", status: "completed", events: [createSceneBeat({ id: "old-scene", presentationMode: "scene" })] },
        { dayIndex: 3, title: "Day 3", status: "current", events: [createSceneBeat({ id: "today", presentationMode: "narrative" })] },
      ],
    });

    assert.match(markup, /你终于来了。/);
    assert.equal((markup.match(/aria-label="提交剧情行动"/g) ?? []).length, 1);
  });

  it("disables input while the Story is generating", () => {
    const scene = createSceneBeat({ id: "pending-scene", presentationMode: "scene" });
    const markup = render({
      days: [{ dayIndex: 3, title: "Day 3", status: "current", events: [scene] }],
      status: "running",
    });

    assert.match(markup, /aria-label="提交剧情行动" disabled=""/);
  });
});
