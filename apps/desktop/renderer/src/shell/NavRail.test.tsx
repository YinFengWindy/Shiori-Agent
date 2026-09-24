/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { buildNavRailViews, NavRail, pluginNavRailViewId, type NavRailPluginEntry } from "./NavRail.js";

type RailOverrides = Partial<Parameters<typeof NavRail>[0]> & { pluginEntries?: NavRailPluginEntry[] };

function renderRail(overrides: RailOverrides = {}) {
  const { pluginEntries, ...props } = overrides;
  return renderToStaticMarkup(
    <NavRail
      activeView={null}
      unreadTotal={0}
      views={buildNavRailViews({ onBackToChat: () => undefined, onOpenRolesWorkspace: () => undefined, pluginEntries })}
      onOpenSearch={() => undefined}
      onOpenSettings={() => undefined}
      {...props}
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

  it("drops native title tooltips in favour of the brand tooltip", () => {
    assert.doesNotMatch(renderRail(), /\stitle="/);
  });

  it("renders search as an action set apart from the view entries", () => {
    const markup = renderRail({ activeView: "messages" });
    const search = /<button[^>]*aria-label="搜索"[^>]*>/.exec(markup)?.[0] ?? "";
    assert.match(search, /rounded-full/);
    assert.match(search, /aria-haspopup="dialog"/);
    assert.doesNotMatch(search, /aria-current/);
    // The divider sits between the search action and the first view entry.
    const divider = markup.indexOf("h-px w-6");
    assert.ok(markup.indexOf('aria-label="搜索"') < divider);
    assert.ok(divider < markup.indexOf('aria-label="消息"'));
  });

  it("advertises each view's shortcut in rail order", () => {
    const markup = renderRail({ pluginEntries: [{ pageId: "demo", label: "Demo", onSelect: () => undefined }] });
    assert.match(markup, /aria-label="消息" aria-keyshortcuts="Ctrl\+1"/);
    assert.match(markup, /aria-label="角色" aria-keyshortcuts="Ctrl\+2"/);
    assert.match(markup, /aria-label="Demo" aria-keyshortcuts="Ctrl\+3"/);
    assert.match(markup, /aria-label="设置" aria-keyshortcuts="Ctrl\+,"/);
    assert.match(markup, /aria-label="搜索" aria-keyshortcuts="Ctrl\+K"/);
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

describe("buildNavRailViews", () => {
  it("numbers views 1 to 9 and leaves the rest without a shortcut", () => {
    const pluginEntries = Array.from({ length: 9 }, (_, index) => ({ pageId: `p${index}`, label: `P${index}`, onSelect: () => undefined }));
    const views = buildNavRailViews({ onBackToChat: () => undefined, onOpenRolesWorkspace: () => undefined, pluginEntries });
    assert.equal(views.length, 11);
    assert.deepEqual(views.slice(0, 3).map((view) => view.id), ["messages", "roles", "plugin:p0"]);
    assert.equal(views[8]?.shortcut, "Ctrl+9");
    assert.equal(views[9]?.shortcut, undefined);
  });
});
