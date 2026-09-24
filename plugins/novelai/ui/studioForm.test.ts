import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { initialStudioForm } from "./novelAiPageStore";
import { buildGeneratePayload, canSubmitStudioForm, clampCustomDimensionInput, resolveStudioRoleId, validateStudioForm } from "./studioForm";

describe("studioForm", () => {
  it("clamps custom sides to digits within 1..1024", () => {
    assert.equal(clampCustomDimensionInput("12a3"), "123");
    assert.equal(clampCustomDimensionInput("4096"), "1024");
    assert.equal(clampCustomDimensionInput("0"), "");
    assert.equal(clampCustomDimensionInput(""), "");
  });

  it("allows 生成 only with a prompt and a complete, in-budget size", () => {
    assert.equal(canSubmitStudioForm({ ...initialStudioForm, prompt: "  " }), false);
    assert.equal(canSubmitStudioForm({ ...initialStudioForm, prompt: "cat" }), true);
    const custom = { ...initialStudioForm, prompt: "cat", sizePreset: "custom" as const };
    assert.equal(canSubmitStudioForm({ ...custom, customWidth: "800" }), false);
    assert.equal(validateStudioForm({ ...custom, customWidth: "800" }), "", "a half-filled size is not an error yet");
    assert.equal(canSubmitStudioForm({ ...custom, customWidth: "1024", customHeight: "1024" }), true);
    assert.match(validateStudioForm({ ...custom, customWidth: "1024", customHeight: "1025" }), /1024 × 1024/);
  });

  it("builds an img2img payload only when a reference image is present", () => {
    const text = buildGeneratePayload({ ...initialStudioForm, roleId: "rin", prompt: "cat" }, "model-a");
    assert.equal(text.mode, "txt2img");
    assert.equal(text.strength, undefined);
    assert.equal(text.session_key, "role:rin");
    assert.equal(text.model, "model-a");
    const image = buildGeneratePayload({ ...initialStudioForm, prompt: "cat", baseImagePath: "D:/a.png", strength: 0.5 }, "model-a");
    assert.equal(image.mode, "img2img");
    assert.equal(image.strength, 0.5);
    assert.equal(image.session_key, "desktop:image-studio");
  });

  it("keeps a valid role choice, else the role open in chat, else the first", () => {
    assert.equal(resolveStudioRoleId("natsu", "rin", ["rin", "natsu"]), "natsu");
    assert.equal(resolveStudioRoleId("", "rin", ["natsu", "rin"]), "rin");
    assert.equal(resolveStudioRoleId("gone", "missing", ["natsu", "rin"]), "natsu");
    assert.equal(resolveStudioRoleId("", "", []), "");
  });
});
