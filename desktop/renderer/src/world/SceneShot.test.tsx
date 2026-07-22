/// <reference types="node" />
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { SceneShot } from "./SceneShot";

describe("SceneShot", () => {
  it("renders the designed developing frame instead of an empty loading card", () => {
    const markup = renderToStaticMarkup(<SceneShot shot={{ id: "shot", prompt: "雨中灯塔", status: "developing", assets: [] }} onRedraw={() => undefined} />);
    assert.match(markup, /data-testid="scene-shot-developing"/);
    assert.match(markup, />正在显影</);
    assert.match(markup, /radial-gradient/);
  });

  it("keeps alternative renders browseable and redraw available", () => {
    const markup = renderToStaticMarkup(<SceneShot shot={{ id: "shot", prompt: "雨中灯塔", status: "ready", activeAssetId: "asset-2", assets: [{ id: "asset-1", imageUrl: "one.png", createdAtLabel: "初稿" }, { id: "asset-2", imageUrl: "two.png", createdAtLabel: "当前" }] }} onRedraw={() => undefined} />);
    assert.match(markup, /aria-label="上一幅画面"/);
    assert.match(markup, /aria-label="下一幅画面"/);
    assert.match(markup, /aria-label="重绘镜头"/);
  });
});
