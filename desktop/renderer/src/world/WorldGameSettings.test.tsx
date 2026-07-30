/// <reference types="node" />
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it } from "node:test";
import { WorldGameSettings } from "./WorldGameSettings";

describe("WorldGameSettings", () => {
  it("renders World-only presentation settings", () => {
    const markup = renderToStaticMarkup(<WorldGameSettings onBack={() => undefined} />);
    assert.match(markup, /data-testid="world-game-settings"/);
    assert.match(markup, />文字速度</);
    assert.match(markup, />自动播放</);
    assert.match(markup, />减少动态效果</);
    assert.match(markup, />语音</);
    assert.match(markup, />环境音</);
  });
});
