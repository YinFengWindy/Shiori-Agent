/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { RoleRecord } from "../shared/types";
import { RolePetPackagesPanel } from "./RolePetPackagesPanel";

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
    asset_categories: [],
    asset_category_bindings: {},
    pet_packages: [{
      id: "mira-pet",
      format: "codex-sprite@1",
      display_name: "Mira Pet",
      manifest_path: "assets/mira/pets/mira-pet/pet.json",
      spritesheet_path: "assets/mira/pets/mira-pet/spritesheet.webp",
      spritesheet_abs: "C:/workspace/mira/spritesheet.webp",
      imported_at: "",
    }],
    selected_pet_package_id: "mira-pet",
    created_at: "",
    updated_at: "",
  };
}

describe("RolePetPackagesPanel", () => {
  it("renders each package as a selectable preview card", () => {
    const markup = renderToStaticMarkup(
      <RolePetPackagesPanel
        role={createRole()}
        disabled={false}
        onImport={() => undefined}
        onRemove={() => undefined}
        onSelect={() => undefined}
      />,
    );

    assert.match(markup, /aria-pressed="true"/);
    assert.match(markup, /width:800%;height:900%/);
    assert.match(markup, /Mira Pet/);
  });
});
