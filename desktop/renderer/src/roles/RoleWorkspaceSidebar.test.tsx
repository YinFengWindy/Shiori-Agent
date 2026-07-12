import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { RoleWorkspaceSidebar } from "./RoleWorkspaceSidebar";

describe("RoleWorkspaceSidebar", () => {
  it("uses the shared secondary sidebar background", () => {
    const markup = renderToStaticMarkup(
      <RoleWorkspaceSidebar
        activeSection="roles-list"
        collapsed={false}
        animating={false}
        width={240}
        onBackToChat={() => undefined}
        onOpenSection={() => undefined}
        onBeginResize={() => undefined}
      />,
    );

    assert.match(markup, /bg-\[#EFF4F9\]/);
    assert.doesNotMatch(markup, /bg-\[#EEF1F5\]/);
  });
});
