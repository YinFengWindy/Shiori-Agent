import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { RoleAssetCategoryGroups } from "./RoleAssetCategoryGroups";

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
});
