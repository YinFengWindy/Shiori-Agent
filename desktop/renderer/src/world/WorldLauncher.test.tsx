/// <reference types="node" />
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it } from "node:test";
import { WorldLauncher } from "./WorldLauncher";
import { createWorldDetails, createWorldSummary } from "./testFixtures";

describe("WorldLauncher", () => {
  it("renders Galgame-style menu with create, load, settings, and exit", () => {
    const markup = renderToStaticMarkup(
      <WorldLauncher
        worlds={[createWorldSummary()]}
        onCreateWorld={() => undefined}
        onLoadWorld={() => undefined}
        onOpenSettings={() => undefined}
        onExit={() => undefined}
      />
    );
    // Check menu items exist
    assert.ok(markup.includes("创建世界"));
    assert.ok(markup.includes("加载世界"));
    assert.ok(markup.includes("设置"));
    assert.ok(markup.includes("退出"));
    // Check logo
    assert.ok(markup.includes("Shiori"));
    // The relative URL must resolve beside renderer-dist/index.html under Electron loadFile().
    assert.ok(markup.includes("url(./assets/backgrounds/default-galgame-bg.png)"));
    assert.doesNotMatch(markup, /url\(['\"]?\/assets\//);
    // Check no old "继续世界" text
    assert.doesNotMatch(markup, /继续世界/);
  });

  it("renders world list only after load menu is opened", () => {
    const markup = renderToStaticMarkup(
      <WorldLauncher
        worlds={[createWorldSummary(createWorldDetails({ name: "雨港" }))]}
        onCreateWorld={() => undefined}
        onLoadWorld={() => undefined}
        onOpenSettings={() => undefined}
        onExit={() => undefined}
      />
    );
    // World list should not be visible initially
    assert.doesNotMatch(markup, /data-testid="world-load-list"/);
    assert.match(markup, />加载世界</);
  });

  it("uses a readable compact menu surface", () => {
    const markup = renderToStaticMarkup(
      <WorldLauncher
        worlds={[]}
        onCreateWorld={() => undefined}
        onLoadWorld={() => undefined}
        onOpenSettings={() => undefined}
        onExit={() => undefined}
      />
    );
    assert.ok(markup.includes("bg-[#111512]/85"));
    assert.ok(markup.includes("overflow-y-auto"));
    assert.ok(markup.includes("calc(100%-32px)"));
    assert.doesNotMatch(markup, /rounded-(?:xl|2xl)/);
  });

  it("does not inject a bounce animation that bypasses motion settings", () => {
    const markup = renderToStaticMarkup(
      <WorldLauncher
        worlds={[]}
        onCreateWorld={() => undefined}
        onLoadWorld={() => undefined}
        onOpenSettings={() => undefined}
        onExit={() => undefined}
      />
    );
    assert.doesNotMatch(markup, /slideUpBounce|<style/);
  });
});
