/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { getSelectedRoleAssetPath } from "./roleAssetSelection";

describe("getSelectedRoleAssetPath", () => {
  it("uses the avatar selection when the library is in avatar mode", () => {
    assert.equal(
      getSelectedRoleAssetPath("avatar", "avatars/mira.png", "featured/mira.png", "fallback.png"),
      "avatars/mira.png",
    );
  });

  it("uses the featured selection when the library is in featured mode", () => {
    assert.equal(
      getSelectedRoleAssetPath("featured", "avatars/mira.png", "featured/mira.png", "fallback.png"),
      "featured/mira.png",
    );
  });

  it("falls back to the first asset when the current mode has no saved selection", () => {
    assert.equal(
      getSelectedRoleAssetPath("avatar", "", "featured/mira.png", "fallback.png"),
      "fallback.png",
    );
  });
});
