import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleCardImportPreview } from "../shared/types";
import { createRoleFormFromImport, readRoleCardImportPreview } from "./roleCardImportState";

describe("roleCardImportState", () => {
  it("copies editable imported fields and starts emotion choices empty", () => {
    const preview: RoleCardImportPreview = {
      import_id: "card-1",
      name: "Mira",
      description: "A quiet archivist",
      system_prompt: "Speak calmly",
      profile: {
        character: { personality: "calm", response_constraints: "Keep replies short" },
      },
    };

    const form = createRoleFormFromImport(readRoleCardImportPreview(preview));

    assert.deepEqual(form, {
      importId: "card-1", name: "Mira", description: "A quiet archivist",
      systemPrompt: "Speak calmly", profile: preview.profile, emotionSelections: {},
    });
  });

  it("rejects responses without a usable staging token", () => {
    for (const payload of [null, [], "card-1", {}, { import_id: "" }, { import_id: "  " }, { import_id: 1 }]) {
      assert.throws(() => readRoleCardImportPreview(payload), /import_id/);
    }
  });
});
