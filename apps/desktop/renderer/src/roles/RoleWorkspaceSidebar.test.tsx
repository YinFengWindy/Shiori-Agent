import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { RoleRecord } from "../shared/types";
import { RoleWorkspaceSidebar, type RoleWorkspaceSectionId } from "./RoleWorkspaceSidebar";

function role(id: string, name: string, description = ""): RoleRecord {
  return { id, name, description, avatar_abs: null } as RoleRecord;
}

const roles = [role("mira", "Mira", "档案管理员"), role("rin", "凛")];

async function mountSidebar(overrides: Partial<Parameters<typeof RoleWorkspaceSidebar>[0]> = {}) {
  const calls: string[] = [];
  const view = await mountTestComponent(
    <RoleWorkspaceSidebar
      activeSection={"roles-list" satisfies RoleWorkspaceSectionId}
      activeRoleId=""
      roles={roles}
      pendingRoleId=""
      bridgeReady
      canImportRoleCard
      collapsed={false}
      animating={false}
      width={240}
      onOpenSection={(section) => calls.push(`section:${section}`)}
      onOpenRole={(roleId) => calls.push(`role:${roleId}`)}
      onImportRoleCard={() => calls.push("import")}
      onBeginResize={() => undefined}
      {...overrides}
    />,
  );
  const button = (name: string) => Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent?.includes(name)) as HTMLButtonElement;
  return { view, calls, button };
}

describe("RoleWorkspaceSidebar", () => {
  it("lists every role with its short description and routes the top actions", async () => {
    const { view, calls, button } = await mountSidebar();
    try {
      assert.match(view.container.textContent ?? "", /Mira档案管理员/);
      assert.match(view.container.textContent ?? "", /凛未填写角色简介/);
      await act(async () => { button("新建").click(); });
      await act(async () => { button("导入角色卡").click(); });
      await act(async () => { button("全部角色").click(); });
      await act(async () => { button("凛").click(); });
      assert.deepEqual(calls, ["section:role-create", "import", "section:roles-list", "role:rin"]);
      assert.equal(button("全部角色").getAttribute("aria-current"), "page");
    } finally { await view.cleanup(); }
  });

  it("marks the role open in detail or assets as current", async () => {
    for (const section of ["role-detail", "role-assets"] as const) {
      const { view } = await mountSidebar({ activeSection: section, activeRoleId: "mira" });
      try {
        const current = view.container.querySelectorAll('[aria-current="page"]');
        assert.equal(current.length, 1);
        assert.equal(current[0]?.getAttribute("data-testid"), "role-workspace-role-mira");
      } finally { await view.cleanup(); }
    }
  });

  it("keeps a pending role and a busy import unavailable", async () => {
    const { view, button } = await mountSidebar({ pendingRoleId: "rin", canImportRoleCard: false });
    try {
      assert.equal(button("凛").disabled, true);
      assert.equal(button("Mira").disabled, false);
      assert.equal(button("导入角色卡").disabled, true);
    } finally { await view.cleanup(); }
  });
});
