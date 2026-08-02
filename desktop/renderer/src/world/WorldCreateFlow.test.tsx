/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { WorldCreateFlow } from "./WorldCreateFlow";

describe("WorldCreateFlow", () => {
  it("starts with a focused role-selection step instead of the three-column workspace", () => {
    const markup = renderToStaticMarkup(<WorldCreateFlow roles={[{ id: "role-1", name: "澪", description: "沉默的守灯人" }]} initialSeed="RAIN-441" onBack={() => undefined} onCreate={() => undefined} />);
    assert.match(markup, />选择角色</);
    assert.match(markup, />步骤 1\/4</);
    assert.match(markup, /aria-label="创建步骤"/);
    assert.match(markup, /aria-label="返回剧情主菜单"/);
    assert.doesNotMatch(markup, /grid-cols-\[220px/);
    assert.doesNotMatch(markup, /<aside/);
    assert.doesNotMatch(markup, />年龄</);
    assert.doesNotMatch(markup, />性别</);
    assert.doesNotMatch(markup, />版本</);
  });

  it("shows the first step action without exposing draft confirmation", () => {
    const markup = renderToStaticMarkup(<WorldCreateFlow roles={[]} initialSeed="RAIN-441" onBack={() => undefined} onCreate={() => undefined} />);
    assert.match(markup, />下一步</);
    assert.doesNotMatch(markup, />角色和玩家资料会在开场时固定下来。/);
  });
});
