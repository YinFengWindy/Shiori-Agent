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
    illustrations: ["assets/a.png", "assets/b.png"],
    illustrations_abs: ["C:/roles/assets/a.png", "C:/roles/assets/b.png"],
    asset_categories: [{ id: "default", name: "默认", allow_role_send: false }],
    asset_category_bindings: {},
    created_at: "",
    updated_at: "",
  };
}

function render(focusedAssetPath = "") {
  return renderToStaticMarkup(
    <RoleAssetCategoryGroups
      role={createRole()}
      bridgeReady
      saving={false}
      focusedAssetPath={focusedAssetPath}
      onPickAssets={() => undefined}
      onFocusAsset={() => undefined}
      onUpdateOrganization={async () => true}
    />,
  );
}

describe("RoleAssetCategoryGroups", () => {
  it("lists every category with its thumbnails and a labeled 新建分类 action", () => {
    const markup = render();

    assert.match(markup, />新建分类</);
    assert.match(markup, /aria-label="收起默认"/);
    assert.equal(markup.match(/aria-label="查看素材"/g)?.length, 2);
    assert.match(markup, /aria-label="上传到默认"/);
  });

  it("puts no delete button on the thumbnails; deleting happens in the preview pane", () => {
    assert.doesNotMatch(render("assets/a.png"), /删除素材/);
  });

  it("marks only the previewed thumbnail as selected", () => {
    const markup = render("assets/b.png");
    assert.equal(markup.match(/aria-pressed="true"[^>]*aria-label="查看素材"/g)?.length, 1);
  });
});
