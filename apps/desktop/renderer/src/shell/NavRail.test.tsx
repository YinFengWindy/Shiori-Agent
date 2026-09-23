/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { NavRail, pluginNavRailViewId } from "./NavRail.js";

function renderRail(overrides?: Partial<Parameters<typeof NavRail>[0]>) {
  return renderToStaticMarkup(
    <NavRail
      activeView={null}
      unreadTotal={0}
      onOpenSearch={() => undefined}
      onBackToChat={() => undefined}
      onOpenRolesWorkspace={() => undefined}
      onOpenSettings={() => undefined}
      {...overrides}
    />,
  );
}

describe("NavRail", () => {
  it("renders only the built-in navigation entries", () => {
    const markup = renderRail();
    const labels = ["搜索", "消息", "角色", "设置"];

    for (const label of labels) {
      assert.match(markup, new RegExp(`aria-label="${label}"`));
    }
    assert.match(markup, /aria-label="主导航"/);
  });

  it("only shows the unread badge on messages when unread traffic exists", () => {
    const quietMarkup = renderRail({ unreadTotal: 0 });
    assert.doesNotMatch(quietMarkup, /bg-danger/);

    const unreadMarkup = renderRail({ unreadTotal: 3 });
    assert.match(unreadMarkup, /aria-label="消息（3 条未读）"/);
    assert.match(unreadMarkup, /bg-danger/);
  });

  it("renders a plugin nav.page entry alongside the built-in navigation, active when selected", () => {
    const markup = renderRail({
      activeView: pluginNavRailViewId("demo"),
      pluginEntries: [{ pageId: "demo", label: "Demo 页面", onSelect: () => undefined }],
    });

    assert.match(markup, /aria-label="Demo 页面"/);
    assert.match(markup, /aria-label="Demo 页面"[^>]*aria-current="page"/);
  });
});
