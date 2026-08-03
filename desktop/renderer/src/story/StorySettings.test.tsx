/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StorySettings } from "./StorySettings";

describe("StorySettings", () => {
  it("renders Story preferences without World presentation controls", () => {
    const markup = renderToStaticMarkup(<StorySettings onBack={() => undefined} />);
    assert.match(markup, /data-testid="story-settings"/);
    assert.match(markup, />文字速度</);
    assert.match(markup, />立即显示全文</);
    assert.match(markup, />动效强度</);
    assert.match(markup, />减少动态效果</);
    assert.match(markup, />语音</);
    assert.match(markup, />环境音</);
    assert.doesNotMatch(markup, /自动播放|快进|World|world/);
  });
});
