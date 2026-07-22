/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { WorldCreateFlow } from "./WorldCreateFlow";

describe("WorldCreateFlow", () => {
  it("asks only for semantic world and first-OC fields and exposes seed controls", () => {
    const markup = renderToStaticMarkup(<WorldCreateFlow roles={[{ id: "role-1", name: "澪", description: "沉默的守灯人" }]} initialSeed="RAIN-441" onRerollSeed={() => "NEW-SEED"} onPreview={() => undefined} onConfirm={() => undefined} />);
    assert.match(markup, />世界轮廓</);
    assert.match(markup, />身份描述</);
    assert.match(markup, />入场时间</);
    assert.match(markup, />世界种子</);
    assert.match(markup, /aria-label="复制世界种子"/);
    assert.match(markup, /aria-label="换一个种子"/);
    assert.doesNotMatch(markup, />年龄</);
    assert.doesNotMatch(markup, />性别</);
    assert.doesNotMatch(markup, />版本</);
  });

  it("renders native identity drafts as editable review items", () => {
    const markup = renderToStaticMarkup(<WorldCreateFlow roles={[]} initialSeed="RAIN-441" draft={{ id: "draft-1", input: { name: "雨港", premise: "潮汐带回名字", rules: "因果不可逆", tone: "克制", selectedRoleIds: ["role-1"], seed: "RAIN-441", firstOc: { name: "岚", identity: "抄写员", entryTime: "第三日", entryLocation: "旧港", primaryGoal: "寻找姐姐" } }, nativeIdentities: [{ roleId: "role-1", roleName: "澪", nativeName: "澪", identity: "守灯人", history: "在港口长大", relationships: "无人知晓", accepted: true }] }} onRerollSeed={() => "NEW-SEED"} onPreview={() => undefined} onConfirm={() => undefined} />);
    assert.match(markup, /aria-label="澪 在地姓名"/);
    assert.match(markup, /aria-label="澪 在地身份"/);
    assert.match(markup, />确认世界与 OC</);
  });
});
