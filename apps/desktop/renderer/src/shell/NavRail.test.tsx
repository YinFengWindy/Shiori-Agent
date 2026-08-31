/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { NavRail } from "./NavRail.js";

function renderRail(overrides?: Partial<Parameters<typeof NavRail>[0]>) {
  return renderToStaticMarkup(
    <NavRail
      activeView={null}
      unreadTotal={0}
      onOpenSearch={() => undefined}
      onBackToChat={() => undefined}
      onOpenRolesWorkspace={() => undefined}
      onOpenImageStudio={() => undefined}
      onOpenStory={() => undefined}
      onOpenSettings={() => undefined}
      {...overrides}
    />,
  );
}

describe("NavRail", () => {
  it("renders the six primary navigation entries in order", () => {
    const markup = renderRail();
    const labels = ["搜索", "消息", "角色", "生图", "故事", "设置"];

    for (const label of labels) {
      assert.match(markup, new RegExp(`aria-label="${label}"`));
    }
    assert.match(markup, /aria-label="主导航"/);
  });

  it("marks the active workspace entry and fills its glyph", () => {
    const markup = renderRail({ activeView: "messages" });

    assert.match(markup, /aria-label="消息"[^>]*aria-current="page"/);
    assert.doesNotMatch(markup, /aria-label="角色"[^>]*aria-current="page"/);
    assert.doesNotMatch(markup, /aria-label="设置"[^>]*aria-current="page"/);
  });

  it("only shows the unread badge on messages when unread traffic exists", () => {
    const quietMarkup = renderRail({ unreadTotal: 0 });
    assert.doesNotMatch(quietMarkup, /bg-\[#DA4B4B\]/);

    const unreadMarkup = renderRail({ unreadTotal: 3 });
    assert.match(unreadMarkup, /aria-label="消息（3 条未读）"/);
    assert.match(unreadMarkup, /bg-\[#DA4B4B\]/);
  });

  it("uses the NovelAI mark for the image workspace entry", () => {
    const markup = renderRail();

    assert.match(markup, /src="[^"]*novelai-logo-dark\.svg"/);
  });
});
