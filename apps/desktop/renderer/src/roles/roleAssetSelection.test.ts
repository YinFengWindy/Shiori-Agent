/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { getNextRoleAssetSelection, getSelectedRoleAssetPath } from "./roleAssetSelection";

describe("getSelectedRoleAssetPath", () => {
  it("uses the avatar selection when the library is in avatar mode", () => {
    assert.equal(
      getSelectedRoleAssetPath("avatar", "avatars/mira.png", "backgrounds/mira.png"),
      "avatars/mira.png",
    );
  });

  it("uses the chat background selection when the library is in chat background mode", () => {
    assert.equal(
      getSelectedRoleAssetPath("chat-background", "avatars/mira.png", "backgrounds/mira.png"),
      "backgrounds/mira.png",
    );
  });

  it("keeps the current mode empty when nothing is selected", () => {
    assert.equal(
      getSelectedRoleAssetPath("avatar", "", "backgrounds/mira.png"),
      "",
    );
  });
});

describe("getNextRoleAssetSelection", () => {
  it("selects a new asset when clicking a different image", () => {
    assert.equal(
      getNextRoleAssetSelection("avatars/mira.png", "backgrounds/other.png"),
      "backgrounds/other.png",
    );
  });

  it("keeps the current selection when clicking the currently selected image", () => {
    assert.equal(
      getNextRoleAssetSelection("avatars/mira.png", "avatars/mira.png"),
      "avatars/mira.png",
    );
  });
});
