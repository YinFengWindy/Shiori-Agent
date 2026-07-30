/// <reference types="node" />
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it } from "node:test";
import { WorldLauncher } from "./WorldLauncher";
import { createWorldDetails, createWorldSummary } from "./testFixtures";

describe("WorldLauncher", () => {
  it("puts create first and exposes load, settings, and exit without an auto-continue action", () => {
    const markup = renderToStaticMarkup(<WorldLauncher worlds={[createWorldSummary()]} onCreateWorld={() => undefined} onLoadWorld={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);
    assert.ok(markup.indexOf(">创建世界<") < markup.indexOf(">加载世界<"));
    assert.ok(markup.indexOf(">加载世界<") < markup.indexOf(">设置<"));
    assert.ok(markup.indexOf(">设置<") < markup.indexOf(">退出<"));
    assert.doesNotMatch(markup, /继续世界/);
  });

  it("renders saved worlds only after the load menu is opened", () => {
    const markup = renderToStaticMarkup(<WorldLauncher worlds={[createWorldSummary(createWorldDetails({ name: "雨港" }))]} onCreateWorld={() => undefined} onLoadWorld={() => undefined} onOpenSettings={() => undefined} onExit={() => undefined} />);
    assert.doesNotMatch(markup, /data-testid="world-load-list"/);
    assert.match(markup, />加载世界</);
  });
});
