/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { TitleBar } from "./TitleBar.js";

function renderTitleBar(sidebarCollapsed: boolean) {
  return renderToStaticMarkup(
    <TitleBar
      sidebarCollapsed={sidebarCollapsed}
      windowMaximized={false}
      canGoBack={false}
      canGoForward={false}
      canRefreshSession={false}
      onToggleSidebar={() => undefined}
      onGoBack={() => undefined}
      onGoForward={() => undefined}
      onRefreshSession={() => undefined}
    />,
  );
}

describe("TitleBar", () => {
  it("uses the restored left divider position when the sidebar is collapsed", () => {
    const markup = renderTitleBar(true);

    assert.match(markup, /aria-label="侧边栏" aria-expanded="false"/);
    assert.match(markup, /before:bottom-\[2\.2px\] before:left-\[0\.8px\] before:top-\[2\.2px\]/);
    assert.doesNotMatch(markup, /before:bottom-0 before:left-\[3\.3px\] before:top-0/);
  });

  it("uses the centered divider position when the sidebar is expanded", () => {
    const markup = renderTitleBar(false);

    assert.match(markup, /aria-label="侧边栏" aria-expanded="true"/);
    assert.match(markup, /before:bottom-0 before:left-\[3\.3px\] before:top-0/);
    assert.doesNotMatch(markup, /before:bottom-\[2\.2px\] before:left-\[0\.8px\] before:top-\[2\.2px\]/);
  });

  it("does not render the removed text menus", () => {
    const markup = renderTitleBar(false);

    assert.doesNotMatch(markup, /aria-label="应用菜单"/);
    for (const label of ["文件", "编辑", "视图", "帮助"]) {
      assert.doesNotMatch(markup, new RegExp(`>${label}<`));
    }
  });
});
