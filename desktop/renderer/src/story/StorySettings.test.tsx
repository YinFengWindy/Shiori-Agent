/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StorySettings } from "./StorySettings";

describe("StorySettings", () => {
  it("renders Story preferences in the launcher's visual language", () => {
    const markup = renderToStaticMarkup(<StorySettings onBack={() => undefined} />);

    assert.match(markup, /data-testid="story-settings"/);
    assert.match(markup, /data-testid="story-settings-backdrop"/);
    assert.match(markup, /data-testid="story-settings-panel"/);
    assert.match(markup, /min-h-full w-full/);
    assert.match(markup, /url\(\.\/assets\/backgrounds\/default-galgame-bg\.png\)/);
    assert.match(markup, /\.\/assets\/branding\/shiori-title-logo\.png/);
    assert.match(markup, />设置</);
    assert.match(markup, /已保存/);
    assert.match(markup, /aria-label="文字速度"/);
    assert.match(markup, /aria-label="动效强度"/);
    assert.match(markup, /role="switch"/);
    assert.match(markup, /aria-checked="false"/);
    assert.match(markup, /type="range"/);
    assert.match(markup, /语音/);
    assert.match(markup, /环境音/);
    assert.doesNotMatch(markup, /max-w-4xl/);
    assert.doesNotMatch(markup, /<select|type="checkbox"/);
    assert.doesNotMatch(markup, /自动播放|快进|World|world/);
  });
});
