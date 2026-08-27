import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import type { RoleRecord } from "../shared/types";
import { RoleAssetCategoryGroups } from "./RoleAssetCategoryGroups";

function createRole(): RoleRecord {
  return {
    id: "mira",
    name: "Mira",
    description: "",
    system_prompt: "mira",
    runtime_config: {},
    avatar: null,
    avatar_abs: null,
    chat_background: null,
    chat_background_abs: null,
    illustrations: [],
    illustrations_abs: [],
    asset_categories: [{ id: "default", name: "默认", allow_role_send: false }],
    asset_category_bindings: {},
    created_at: "",
    updated_at: "",
  };
}

describe("RoleAssetCategoryGroups", () => {
  it("keeps back and add-category actions in the same toolbar", () => {
    const markup = renderToStaticMarkup(
      <RoleAssetCategoryGroups
        role={null}
        bridgeReady
        saving={false}
        selectedAssetPath=""
        onBackToDetail={() => undefined}
        onPickAssets={() => undefined}
        onRemoveAsset={() => undefined}
        onSelectAsset={() => undefined}
        onUpdateOrganization={async () => true}
      />,
    );

    assert.match(markup, /aria-label="返回角色详情"/);
    assert.match(markup, /aria-label="新建分类"/);
    assert.match(markup, /class="flex items-center justify-between px-2 pb-3"/);
  });

  it("keeps the back action flat and centers the category caret with a fixed-size icon", () => {
    const markup = renderToStaticMarkup(
      <RoleAssetCategoryGroups
        role={createRole()}
        bridgeReady
        saving={false}
        selectedAssetPath=""
        onBackToDetail={() => undefined}
        onPickAssets={() => undefined}
        onRemoveAsset={() => undefined}
        onSelectAsset={() => undefined}
        onUpdateOrganization={async () => true}
      />,
    );

    const backButtonClass = markup.match(/<button class="([^"]+)" type="button" aria-label="返回角色详情"/)?.[1] ?? "";
    assert.doesNotMatch(backButtonClass, /shadow/);
    assert.match(markup, /aria-label="展开默认"[^>]*><svg[^>]*class="h-4 w-4 shrink-0 stroke-current transition-transform"/);
  });
});
