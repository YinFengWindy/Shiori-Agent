import assert from "node:assert/strict";
import { describe, it } from "node:test";

import type { RoleRecord } from "../shared/types";
import {
  groupRoleAssetsByCategory,
  moveRoleAssetToCategory,
  removeRoleAssetCategory,
} from "./roleAssetCategories";

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
    illustrations: ["assets/mira/a.png", "assets/mira/b.png"],
    illustrations_abs: ["C:/a.png", "C:/b.png"],
    asset_categories: [
      { id: "default", name: "默认", allow_role_send: false },
      { id: "reactions", name: "表情包", allow_role_send: true },
    ],
    asset_category_bindings: {
      "assets/mira/a.png": "default",
      "assets/mira/b.png": "reactions",
    },
    created_at: "",
    updated_at: "",
  };
}

describe("roleAssetCategories", () => {
  it("groups each asset into its single persisted category", () => {
    const grouped = groupRoleAssetsByCategory(createRole());

    assert.deepEqual(grouped.get("default")?.map((item) => item.relPath), ["assets/mira/a.png"]);
    assert.deepEqual(grouped.get("reactions")?.map((item) => item.relPath), ["assets/mira/b.png"]);
  });

  it("moves one asset without mutating the current bindings", () => {
    const current = createRole().asset_category_bindings;
    const moved = moveRoleAssetToCategory(current, "assets/mira/a.png", "reactions");

    assert.notEqual(moved, current);
    assert.equal(moved["assets/mira/a.png"], "reactions");
  });

  it("reassigns assets before removing a category", () => {
    const role = createRole();
    const result = removeRoleAssetCategory(
      role.asset_categories,
      role.asset_category_bindings,
      "reactions",
      "default",
    );

    assert.deepEqual(result.categories.map((item) => item.id), ["default"]);
    assert.equal(result.bindings["assets/mira/b.png"], "default");
  });
});
