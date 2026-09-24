import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { act } from "react";
import { createEmptyRoleForm } from "../app/appState";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { RoleRecord } from "../shared/types";

// Created with an avatar: it lives next to the library, not in it.
const role: RoleRecord = {
  id: "mira",
  name: "Mira",
  description: "",
  system_prompt: "mira",
  runtime_config: {},
  avatar: "avatar-1.png",
  avatar_abs: "C:/roles/avatar-1.png",
  chat_background: null,
  chat_background_abs: null,
  illustrations: ["assets/a.png"],
  illustrations_abs: ["C:/roles/assets/a.png"],
  asset_categories: [{ id: "default", name: "默认", allow_role_send: false }],
  asset_category_bindings: { "assets/a.png": "default" },
  created_at: "",
  updated_at: "",
};

// Imported after a DOM exists: the dialog library reads browser globals at module load.
let RoleAssetsPage: typeof import("./RoleAssetsPage").RoleAssetsPage;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ RoleAssetsPage } = await import("./RoleAssetsPage"));
  await environment.cleanup();
});

async function flush() {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
}

const windowGlobals = { miraDesktop: { localAssetUrl: (path: string) => `asset://${path}`, invoke: async () => ({ error: null, payload: { plugins: [] } }), onEvent: () => () => undefined } };

async function mountPage(callbacks: { removed?: string[]; saved?: unknown[] } = {}) {
  return mountTestComponent(
    <RoleAssetsPage
      activeRole={role}
      bridgeReady
      savingSelection={false}
      roleForm={createEmptyRoleForm()}
      selectedAvatarAsset="avatar-1.png"
      selectedChatBackground=""
      onBackToDetail={() => undefined}
      onPickAssets={() => undefined}
      onRemoveAsset={(path) => { callbacks.removed?.push(path); }}
      onPluginRoleDataChanged={() => undefined}
      onSelectAvatarAsset={() => undefined}
      onSelectChatBackground={() => undefined}
      onUpdateRoleForm={() => undefined}
      onUpdateAssetOrganization={async () => true}
      onSaveSelections={(selection) => { callbacks.saved?.push(selection); }}
    />,
    { windowGlobals },
  );
}

describe("RoleAssetsPage", () => {
  it("previews the avatar picked at creation instead of reporting none (regression)", async () => {
    const view = await mountPage();
    try {
      const preview = view.container.querySelector("[data-testid=\"role-asset-preview\"]");
      assert.match(preview?.innerHTML ?? "", /asset:\/\/C:\/roles\/avatar-1\.png/);
      assert.match(preview?.textContent ?? "", /当前头像/);
      assert.doesNotMatch(preview?.textContent ?? "", /未设置头像/);
    } finally { await view.cleanup(); }
  });

  it("labels the modes by what they set", async () => {
    const view = await mountPage();
    try {
      const tabs = Array.from(view.container.querySelectorAll("[role=\"tab\"]")).map((tab) => tab.textContent);
      assert.deepEqual(tabs, ["头像", "聊天背景", "心情立绘"]);
    } finally { await view.cleanup(); }
  });

  it("sets a clicked image only through the explicit 设为头像 action", async () => {
    const saved: unknown[] = [];
    const view = await mountPage({ saved });
    try {
      await act(async () => view.container.querySelector<HTMLButtonElement>("[aria-label=\"查看素材\"]")!.click());
      assert.deepEqual(saved, []);
      await act(async () => view.container.querySelector<HTMLButtonElement>("[data-testid=\"apply-role-asset\"]")!.click());
      assert.deepEqual(saved, [{ avatarAsset: "assets/a.png" }]);
    } finally { await view.cleanup(); }
  });

  it("deletes a library image from the preview pane only once confirmed", async () => {
    const removed: string[] = [];
    const view = await mountPage({ removed });
    try {
      // The creation avatar is not a library image: nothing to delete yet.
      assert.equal(view.container.querySelector("[aria-label=\"删除素材\"]"), null);
      await act(async () => view.container.querySelector<HTMLButtonElement>("[aria-label=\"查看素材\"]")!.click());
      const deleteButton = view.container.querySelector<HTMLButtonElement>("[aria-label=\"删除素材\"]");
      assert.ok(deleteButton);

      await act(async () => deleteButton.click());
      await flush();
      assert.deepEqual(removed, []);
      const dialog = document.querySelector("[role=\"dialog\"]");
      assert.match(dialog?.textContent ?? "", /删除素材/);
      const confirm = Array.from(dialog?.querySelectorAll("button") ?? []).find((item) => item.textContent === "删除");
      await act(async () => confirm?.click());
      assert.deepEqual(removed, ["assets/a.png"]);
    } finally { await view.cleanup(); }
  });
});
