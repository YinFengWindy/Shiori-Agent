/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { ModelRegistrationFormData } from "../../../src/shared.js";
import type { RoleRecord } from "../shared/types.js";
import { runtimeConfigForSelection, selectionFromRole } from "./chatModelSelection.js";

const registrations: ModelRegistrationFormData[] = [
  { id: "chat", provider: "openai", baseUrl: "", apiKey: "", model: "gpt-chat", effort: "none" },
  { id: "vision", provider: "openai", baseUrl: "", apiKey: "", model: "gpt-vision", effort: "high" },
];

function role(runtimeConfig: Record<string, unknown>): RoleRecord {
  return { id: "mira", name: "Mira", runtime_config: runtimeConfig } as RoleRecord;
}

describe("chat model selection", () => {
  it("falls back to the selected registration effort and preserves role overrides", () => {
    const fallback = selectionFromRole(role({ dialogue_model_registration_id: "vision" }), registrations);
    assert.equal(fallback.dialogueEffort, "high");
    assert.equal(fallback.visualEffort, "high");

    const invalidOverride = selectionFromRole(role({
      dialogue_model_registration_id: "vision",
      dialogue_model_effort: "invalid",
    }), registrations);
    assert.equal(invalidOverride.dialogueEffort, "high");

    const override = selectionFromRole(role({
      dialogue_model_registration_id: "chat",
      dialogue_model_effort: "max",
      visual_model_effort: "low",
    }), registrations);
    assert.equal(override.dialogueEffort, "max");
    assert.equal(override.visualEffort, "low");
  });

  it("writes effort changes alongside the role model selections", () => {
    const selection = selectionFromRole(role({ dialogue_model_registration_id: "chat" }), registrations);
    assert.deepEqual(runtimeConfigForSelection(selection, "dialogueEffort", "low"), {
      dialogue_model_registration_id: "chat",
      visual_model_registration_id: "",
      dialogue_model_effort: "low",
      visual_model_effort: "none",
    });
  });
});
