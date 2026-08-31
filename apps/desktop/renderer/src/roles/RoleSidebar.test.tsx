/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { RoleSidebar } from "./RoleSidebar.js";

function renderRoleSidebar() {
  return renderToStaticMarkup(
    <RoleSidebar
      roles={[]}
      activeRoleId=""
      unreadCounts={{}}
      bridgeReady
      collapsed={false}
      animating={false}
      width={280}
      onOpenRole={() => undefined}
      onBeginResize={() => undefined}
    />,
  );
}

describe("RoleSidebar", () => {
  it("renders the conversation list without the removed section title", () => {
    const markup = renderRoleSidebar();

    assert.match(markup, /data-testid="role-list"/);
    assert.doesNotMatch(markup, />对话<\/div>/);
  });
});
