/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { WorldCreateFlow } from "./WorldCreateFlow";

describe("WorldCreateFlow", () => {
  it("keeps the three-column layout while collecting Story and player fields", () => {
    const markup = renderToStaticMarkup(<WorldCreateFlow roles={[{ id: "role-1", name: "澪", description: "沉默的守灯人" }]} initialSeed="RAIN-441" onBack={() => undefined} onRerollSeed={() => "NEW-SEED"} onPreview={() => undefined} onConfirm={() => undefined} />);
    assert.match(markup, />开场设定</);
    assert.match(markup, />选择角色</);
    assert.match(markup, />玩家资料</);
    assert.match(markup, />外貌</);
    assert.match(markup, /aria-label="返回剧情主菜单"/);
    assert.doesNotMatch(markup, />年龄</);
    assert.doesNotMatch(markup, />性别</);
    assert.doesNotMatch(markup, />版本</);
  });

  it("renders the local confirmation after the player completes the form", () => {
    const markup = renderToStaticMarkup(<WorldCreateFlow roles={[]} initialSeed="RAIN-441" draft={{ id: "draft-1", input: { name: "雨港", premise: "潮汐带回名字", rules: "因果不可逆", tone: "克制", selectedRoleIds: ["role-1"], seed: "RAIN-441", firstOc: { name: "岚", identity: "抄写员", entryTime: "第三日", entryLocation: "旧港", primaryGoal: "寻找姐姐" } }, nativeIdentities: [{ roleId: "role-1", roleName: "澪", nativeName: "澪", identity: "守灯人", history: "在港口长大", relationships: "无人知晓", accepted: true }] }} onBack={() => undefined} onRerollSeed={() => "NEW-SEED"} onPreview={() => undefined} onConfirm={() => undefined} />);
    assert.match(markup, />开始剧情</);
    assert.match(markup, />角色和玩家资料会在开场时固定下来。/);
    assert.match(markup, />开始</);
  });
});
