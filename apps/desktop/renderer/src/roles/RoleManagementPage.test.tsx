import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { RoleRecord } from "../shared/types";
import { RoleManagementPage } from "./RoleManagementPage";

function role(id: string, overrides: Partial<RoleRecord> = {}): RoleRecord {
  return {
    id, name: id, description: "", system_prompt: "", runtime_config: {},
    avatar: null, avatar_abs: null, chat_background: null, chat_background_abs: null,
    illustrations: [], illustrations_abs: [], asset_categories: [], asset_category_bindings: {},
    created_at: "", updated_at: "",
    ...overrides,
  };
}

function render(roles: RoleRecord[], pending: Parameters<typeof RoleManagementPage>[0]["pendingCardAction"] = null) {
  return renderToStaticMarkup(
    <RoleManagementPage
      activeRoleId=""
      bridgeReady
      canImportRoleCard
      pendingCardAction={pending}
      roles={roles}
      onOpenRoleDetail={() => undefined}
      onGoToChat={() => undefined}
      onDeleteRole={() => undefined}
      onCreateRole={() => undefined}
      onImportRoleCard={() => undefined}
    />,
  );
}

describe("RoleManagementPage", () => {
  it("never nests a button inside another button", () => {
    const markup = render([role("rin", { chat_background_abs: "C:/r/bg.png" }), role("kaede")]);
    assert.doesNotMatch(markup, /<button[^>]*>(?:(?!<\/button>).)*<button/);
  });

  it("draws a portrait card with its scrim, and the designed placeholder without one", () => {
    const markup = render([role("rin", { chat_background_abs: "C:/r/bg.png" }), role("kaede")]);
    assert.match(markup, /data-testid="role-management-card-rin"[^>]*data-has-portrait="true"/);
    assert.match(markup, /data-testid="role-management-card-kaede"[^>]*data-has-portrait="false"/);
    assert.equal(markup.match(/data-testid="role-portrait-placeholder"/g)?.length, 1);
  });

  it("keeps secondary actions in a per-card overflow menu", () => {
    const markup = render([role("rin")]);
    assert.match(markup, /data-testid="role-card-more-rin"/);
    assert.match(markup, /aria-label="rin 的更多操作"/);
    assert.doesNotMatch(markup, /删除角色 rin/);
  });

  it("blocks a card while it is being deleted", () => {
    const markup = render([role("rin")], { roleId: "rin", action: "delete" });
    assert.match(markup, /data-testid="role-card-open-rin"[^>]*disabled=""/);
    assert.match(markup, /aria-label="正在删除角色"/);
  });

  it("offers create and import from the empty list", () => {
    const markup = render([]);
    assert.match(markup, /data-testid="role-management-empty"/);
    assert.match(markup, />新建角色</);
    assert.match(markup, />导入角色卡</);
  });

  it("has 吟风 front the empty list (static renders see the default: 看板娘 on)", () => {
    const markup = render([]);
    assert.match(markup, /data-testid="mascot-medium"/);
    assert.match(markup, /一个角色都没有/);
  });
});
