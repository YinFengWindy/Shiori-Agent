/// <reference types="node" />
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it } from "node:test";
import { WorldLoadingScreen } from "./WorldLoadingScreen";

describe("WorldLoadingScreen", () => {
  it("renders staged progress for initial World entry", () => {
    const markup = renderToStaticMarkup(<WorldLoadingScreen mode="listing" />);
    assert.match(markup, /data-testid="world-loading-screen"/);
    assert.match(markup, /url\(\.\/assets\/backgrounds\/default-galgame-bg\.png\)/);
    assert.doesNotMatch(markup, /url\(['\"]?\/assets\//);
    assert.match(markup, />读取世界</);
    assert.match(markup, />恢复演出</);
    assert.match(markup, />准备舞台</);
    assert.doesNotMatch(markup, /spinner|圆形/);
    assert.doesNotMatch(markup, /animate-pulse|width:66/);
  });

  it("shows only measured progress after a long load", () => {
    const markup = renderToStaticMarkup(<WorldLoadingScreen mode="world" elapsedMs={2_100} loaded={2} total={4} />);
    assert.match(markup, /role="progressbar"/);
    assert.match(markup, /aria-valuenow="2"/);
    assert.match(markup, /2 \/ 4/);
    assert.match(markup, /width:50%/);
  });

  it("offers retry and back actions after a world load failure", () => {
    const markup = renderToStaticMarkup(<WorldLoadingScreen mode="world" error="加载失败" onRetry={() => undefined} onBack={() => undefined} />);
    assert.match(markup, /role="alert"/);
    assert.match(markup, />重试</);
    assert.match(markup, />返回</);
  });
});
