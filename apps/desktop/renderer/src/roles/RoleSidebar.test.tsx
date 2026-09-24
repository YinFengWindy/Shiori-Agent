import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { RoleSidebar } from "./RoleSidebar";

function renderEmpty(bridgeReady: boolean, onCreateRole: () => void) {
  return mountTestComponent(
    <RoleSidebar
      roles={[]}
      activeRoleId=""
      unreadCounts={{}}
      bridgeReady={bridgeReady}
      collapsed={false}
      animating={false}
      width={220}
      onOpenRole={() => undefined}
      onCreateRole={onCreateRole}
      onBeginResize={() => undefined}
    />,
  );
}

describe("RoleSidebar", () => {
  it("shows a friendly empty state with 新建角色 once roles have loaded and there are none", async () => {
    let created = 0;
    const view = await renderEmpty(true, () => { created += 1; });
    try {
      const empty = view.container.querySelector('[data-testid="role-list-empty"]');
      assert.ok(empty);
      const button = empty.querySelector("button");
      assert.equal(button?.textContent, "新建角色");
      await act(async () => { button?.click(); });
      assert.equal(created, 1);
    } finally { await view.cleanup(); }
  });

  it("stays blank while the bridge is not ready, when the list simply has not loaded", async () => {
    const view = await renderEmpty(false, () => undefined);
    try {
      assert.equal(view.container.querySelector('[data-testid="role-list-empty"]'), null);
    } finally { await view.cleanup(); }
  });
});
