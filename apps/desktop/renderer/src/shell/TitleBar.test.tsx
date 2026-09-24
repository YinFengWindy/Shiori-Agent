/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { TitleBar } from "./TitleBar.js";

describe("TitleBar", () => {
  it("names the reload action after what it reloads: the role's one conversation", () => {
    const markup = renderToStaticMarkup(
      <TitleBar
        sidebarCollapsed={false}
        windowMaximized={false}
        canGoBack
        canGoForward={false}
        canRefreshSession
        onToggleSidebar={() => undefined}
        onGoBack={() => undefined}
        onGoForward={() => undefined}
        onRefreshSession={() => undefined}
      />,
    );
    assert.match(markup, /aria-label="重新载入对话"/);
    assert.doesNotMatch(markup, /刷新会话/);
    assert.match(markup, /aria-label="侧边栏" aria-expanded="true"/);
  });
});
