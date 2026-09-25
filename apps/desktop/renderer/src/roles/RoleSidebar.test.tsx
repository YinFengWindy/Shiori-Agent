import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { appearancePrefsStorageKey } from "../shared/appearancePrefs";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import { resetAppearancePrefsCache } from "../shared/useAppearancePrefs";
import { RoleSidebar } from "./RoleSidebar";

function emptySidebar(bridgeReady: boolean, onCreateRole: () => void) {
  return (
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
    />
  );
}

function renderEmpty(bridgeReady: boolean, onCreateRole: () => void) {
  resetAppearancePrefsCache();
  return mountTestComponent(emptySidebar(bridgeReady, onCreateRole));
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

describe("RoleSidebar chat previews", () => {
  const role = {
    id: "mira", name: "Mira", description: "", system_prompt: "", runtime_config: {},
    avatar: null, avatar_abs: null, chat_background: null, chat_background_abs: null,
    illustrations: [], illustrations_abs: [], asset_categories: [], asset_category_bindings: {},
    created_at: "", updated_at: "",
    last_message: { role: "assistant", content: "**早呀**，今天也要加油", timestamp: new Date().toISOString(), has_media: false },
  };

  function render(activeRoleId: string, unreadCounts: Record<string, number>, activeRolePreview: { text: string; timestamp: string } | null = null) {
    return mountTestComponent(
      <RoleSidebar
        roles={[role]}
        activeRoleId={activeRoleId}
        unreadCounts={unreadCounts}
        activeRolePreview={activeRolePreview}
        bridgeReady
        collapsed={false}
        animating={false}
        width={260}
        onOpenRole={() => undefined}
        onCreateRole={() => undefined}
        onBeginResize={() => undefined}
      />,
    );
  }

  it("shows the bridge preview flattened to one line, with an unread count", async () => {
    const view = await render("", { mira: 3 });
    try {
      assert.equal(view.container.querySelector('[data-testid="role-preview-mira"]')?.textContent, "早呀，今天也要加油");
      assert.equal(view.container.querySelector('[data-testid="role-unread-mira"]')?.textContent, "3");
    } finally { await view.cleanup(); }
  });

  it("lets the open conversation override the active role's preview", async () => {
    const view = await render("mira", {}, { text: "你：晚安", timestamp: "" });
    try {
      assert.equal(view.container.querySelector('[data-testid="role-preview-mira"]')?.textContent, "你：晚安");
      assert.equal(view.container.querySelector('[data-testid="role-unread-mira"]'), null);
    } finally { await view.cleanup(); }
  });

  it("has 吟风 say the empty state with the 看板娘 on (the default)", async () => {
    const view = await renderEmpty(true, () => undefined);
    try {
      const empty = view.container.querySelector('[data-testid="role-list-empty"]');
      assert.equal(empty?.querySelector('[data-testid="mascot-medium"]')?.getAttribute("data-expression"), "pout");
      assert.match(empty?.textContent ?? "", /一个角色都没有/);
    } finally { await view.cleanup(); }
  });

  it("keeps the plain empty state with the 看板娘 off", async () => {
    resetAppearancePrefsCache();
    const view = await mountTestComponent(<div />);
    try {
      window.localStorage.setItem(appearancePrefsStorageKey, JSON.stringify({ version: 1, backdropMotion: true, mascot: false }));
      await view.render(emptySidebar(true, () => undefined));
      const empty = view.container.querySelector('[data-testid="role-list-empty"]');
      assert.equal(empty?.querySelector('[data-testid="mascot-medium"]'), null);
      assert.match(empty?.textContent ?? "", /还没有角色/);
      assert.equal(empty?.querySelector("button")?.textContent, "新建角色");
    } finally {
      await view.cleanup();
      resetAppearancePrefsCache();
    }
  });
});
