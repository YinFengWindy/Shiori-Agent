import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { currentRoleAsset, resolveRoleAssetPreview, roleAssetModes } from "./roleAssetPreview";

// A role created with an avatar: `avatar` is imported next to the library, not into it.
const role = {
  avatar: "avatar-3f2a.png",
  avatar_abs: "C:/roles/mira/avatar-3f2a.png",
  chat_background: "a/bg.webp",
  chat_background_abs: "C:/roles/mira/a/bg.webp",
  illustrations: ["a/bg.webp", "a/smile.webp"],
  illustrations_abs: ["C:/roles/mira/a/bg.webp", "C:/roles/mira/a/smile.webp"],
};

describe("currentRoleAsset", () => {
  it("finds the avatar picked at creation even though it is not in the asset library", () => {
    const current = currentRoleAsset("avatar", role, role.avatar, role.chat_background);
    assert.deepEqual(current, { relPath: "avatar-3f2a.png", absPath: "C:/roles/mira/avatar-3f2a.png", inLibrary: false, isCurrent: true });
  });

  it("resolves a library image set as the chat background", () => {
    assert.deepEqual(currentRoleAsset("chat-background", role, role.avatar, role.chat_background), {
      relPath: "a/bg.webp", absPath: "C:/roles/mira/a/bg.webp", inLibrary: true, isCurrent: true,
    });
  });

  it("reports nothing when the mode has nothing set, and never for mood bindings", () => {
    assert.equal(currentRoleAsset("avatar", role, "", ""), null);
    assert.equal(currentRoleAsset("mood-binding", role, role.avatar, role.chat_background), null);
  });
});

describe("resolveRoleAssetPreview", () => {
  it("shows the current avatar when nothing is clicked (regression: 「当前未设置头像」 for a creation avatar)", () => {
    const preview = resolveRoleAssetPreview({ mode: "avatar", role, focusedPath: "", selectedAvatarAsset: role.avatar, selectedChatBackground: "" });
    assert.equal(preview?.absPath, "C:/roles/mira/avatar-3f2a.png");
    assert.equal(preview?.isCurrent, true);
  });

  it("prefers the clicked library image and tells whether it is already set", () => {
    const clicked = resolveRoleAssetPreview({ mode: "chat-background", role, focusedPath: "a/smile.webp", selectedAvatarAsset: role.avatar, selectedChatBackground: role.chat_background });
    assert.deepEqual(clicked, { relPath: "a/smile.webp", absPath: "C:/roles/mira/a/smile.webp", inLibrary: true, isCurrent: false });
    const same = resolveRoleAssetPreview({ mode: "chat-background", role, focusedPath: "a/bg.webp", selectedAvatarAsset: role.avatar, selectedChatBackground: role.chat_background });
    assert.equal(same?.isCurrent, true);
  });

  it("ignores a clicked path that left the library (e.g. just deleted)", () => {
    const preview = resolveRoleAssetPreview({ mode: "mood-binding", role, focusedPath: "a/gone.webp", selectedAvatarAsset: "", selectedChatBackground: "" });
    assert.equal(preview, null);
  });
});

describe("roleAssetModes", () => {
  it("names each mode after what it sets", () => {
    assert.deepEqual(roleAssetModes.map((mode) => `${mode.id}:${mode.label}`), ["avatar:头像", "chat-background:聊天背景", "mood-binding:心情立绘"]);
  });
});
