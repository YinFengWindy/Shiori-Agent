/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryCgGallerySurface } from "./StoryCgGallerySurface";
import type { StoryCgGallery } from "./types";

const stories: StoryCgGallery[] = [{
  storyId: "story-1",
  title: "雨港",
  status: "active",
  createdAt: "2026-08-02T10:00:00+08:00",
  items: [{
    id: "resource-1",
    storyId: "story-1",
    kind: "background",
    visualType: "scene",
    sceneKey: "default",
    status: "ready",
    path: "D:\\stories\\opening.png",
    prompt: "anime screencap",
    sourceTurnId: "turn-1",
    sequence: 1,
    errorCode: null,
    createdAt: "2026-08-02T10:00:00+08:00",
    updatedAt: "2026-08-02T10:00:00+08:00",
  }],
}];

describe("StoryCgGallerySurface", () => {
  it("renders a full-screen Story gallery grouped by story", () => {
    const markup = renderToStaticMarkup(<StoryCgGallerySurface stories={stories} busy={false} error="" onRetry={() => undefined} onBack={() => undefined} />);
    assert.match(markup, /data-testid="story-cg-gallery"/);
    assert.match(markup, /data-testid="story-cg-gallery-panel"/);
    assert.match(markup, />CG 鉴赏</);
    assert.match(markup, />雨港</);
    assert.match(markup, /shiori-asset:\/\/local\/unavailable/);
    assert.doesNotMatch(markup, />1 张</);
    assert.doesNotMatch(markup, />1 \/ 1</);
    assert.doesNotMatch(markup, /text-\[#B64B75\]/);
  });

  it("shows a retry command for failed resources", () => {
    const failed = [{ ...stories[0], items: [{ ...stories[0].items[0], status: "failed" as const, path: null, errorCode: "provider_not_configured" }] }];
    const markup = renderToStaticMarkup(<StoryCgGallerySurface stories={failed} busy={false} error="" onRetry={() => undefined} onBack={() => undefined} />);
    assert.match(markup, /data-testid="story-cg-resource-failed"/);
    assert.match(markup, /aria-label="图片生成工具未配置"/);
    assert.match(markup, />图片生成工具未配置</);
    assert.match(markup, /title="provider_not_configured"/);
    assert.match(markup, />重试</);
  });
});
