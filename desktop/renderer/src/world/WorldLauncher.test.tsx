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
    assert.ok(markup.includes("创建剧情"));
    assert.ok(markup.includes("加载剧情"));
    assert.ok(markup.includes("设置"));
    assert.ok(markup.includes("退出"));
    // Check bilingual title wordmark and its bundled path.
    assert.ok(markup.includes("栞 / SHIORI"));
    assert.ok(markup.includes("./assets/branding/shiori-title-logo.png"));
    // The relative URL must resolve beside renderer-dist/index.html under Electron loadFile().
    assert.ok(markup.includes("url(./assets/backgrounds/default-galgame-bg.png)"));
    assert.doesNotMatch(markup, /url\(['\"]?\/assets\//);
    assert.doesNotMatch(markup, /创建世界|加载世界/);
  });

  it("renders the Story list only after load menu is opened", () => {
    const markup = renderToStaticMarkup(
      <WorldLauncher
        worlds={[createWorldSummary(createWorldDetails({ name: "雨港" }))]}
        onCreateWorld={() => undefined}
        onLoadWorld={() => undefined}
        onOpenSettings={() => undefined}
        onExit={() => undefined}
      />
    );
    assert.doesNotMatch(markup, /data-testid="world-load-list"/);
    assert.match(markup, />加载剧情</);
  });

  it("uses a cinematic command rail instead of a boxed utility menu", () => {
    const markup = renderToStaticMarkup(
      <WorldLauncher
        worlds={[]}
        onCreateWorld={() => undefined}
        onLoadWorld={() => undefined}
        onOpenSettings={() => undefined}
        onExit={() => undefined}
      />
    );
    assert.match(markup, /data-testid="story-menu-backdrop"/);
    assert.match(markup, /data-testid="story-menu-title"/);
    assert.match(markup, /data-testid="world-launcher-command-rail"/);
    assert.match(markup, /border-l-2/);
    assert.doesNotMatch(markup, /bg-\[#111512\]\/85/);
  });

  it("keeps the wordmark tight to the upper left and dims the bright backdrop", () => {
    const markup = renderToStaticMarkup(
      <WorldLauncher
        worlds={[]}
        onCreateWorld={() => undefined}
        onLoadWorld={() => undefined}
        onOpenSettings={() => undefined}
        onExit={() => undefined}
      />
    );

    assert.match(markup, /left-\[clamp\(12px,2vw,28px\)\]/);
    assert.match(markup, /top-\[clamp\(12px,2vh,28px\)\]/);
    assert.match(markup, /w-\[min\(18rem,calc\(100vw-24px\)\)\]/);
    assert.match(markup, /bg-\[#130E18\]\/68/);
    assert.doesNotMatch(markup, /bg-black\/10/);
  });

  it("keeps the main menu in the renderer without injected animation styles", () => {
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
