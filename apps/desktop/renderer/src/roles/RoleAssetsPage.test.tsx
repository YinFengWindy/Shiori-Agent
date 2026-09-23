import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { act } from "react";
import { createEmptyRoleForm } from "../app/appState";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { RoleRecord } from "../shared/types";

const role: RoleRecord = {
  id: "mira",
  name: "Mira",
  description: "",
  system_prompt: "mira",
  runtime_config: {},
  avatar: null,
  avatar_abs: null,
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

describe("RoleAssetsPage asset deletion", () => {
  it("asks before deleting from either delete button and only removes once confirmed", async () => {
    const removed: string[] = [];
    const view = await mountTestComponent(
      <RoleAssetsPage
        activeRole={role}
        bridgeReady
        savingSelection={false}
        roleForm={createEmptyRoleForm()}
        selectedAvatarAsset=""
        selectedChatBackground=""
        onBackToDetail={() => undefined}
        onPickAssets={() => undefined}
        onRemoveAsset={(path) => { removed.push(path); }}
        onPluginRoleDataChanged={() => undefined}
        onSelectAvatarAsset={() => undefined}
        onSelectChatBackground={() => undefined}
        onUpdateRoleForm={() => undefined}
        onUpdateAssetOrganization={async () => true}
        onSaveSelections={() => undefined}
      />,
      { windowGlobals: { miraDesktop: { localAssetUrl: (path: string) => `asset://${path}`, invoke: async () => ({ error: null, payload: { plugins: [] } }), onEvent: () => () => undefined } } },
    );
    try {
      const deleteButtons = view.container.querySelectorAll<HTMLButtonElement>('[aria-label="删除素材"]');
      assert.equal(deleteButtons.length, 2);
      for (const button of Array.from(deleteButtons)) {
        await act(async () => button.click());
        await flush();
        assert.deepEqual(removed, []);
        const dialog = document.querySelector('[role="dialog"]');
        assert.match(dialog?.textContent ?? "", /删除素材/);
        const cancel = Array.from(dialog?.querySelectorAll("button") ?? []).find((item) => item.textContent === "取消");
        await act(async () => cancel?.click());
        await flush();
      }
      await act(async () => deleteButtons[0]!.click());
      await flush();
      const confirm = Array.from(document.querySelectorAll('[role="dialog"] button')).find((item) => item.textContent === "删除") as HTMLButtonElement | undefined;
      await act(async () => confirm?.click());
      assert.deepEqual(removed, ["assets/a.png"]);
    } finally { await view.cleanup(); }
  });
});
