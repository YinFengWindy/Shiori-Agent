/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { resolveRightSidebarDragUpdate } from "./useRightSidebarState";

describe("resolveRightSidebarDragUpdate", () => {
  it("returns a zero-width preview below the collapse threshold", () => {
    assert.deepEqual(resolveRightSidebarDragUpdate(1250, 1320, 220, 400, 110), {
      collapsed: true,
      previewWidth: 0,
      expandedWidth: null,
    });
  });

  it("clamps expanded previews while preserving the committed width", () => {
    assert.deepEqual(resolveRightSidebarDragUpdate(900, 1320, 220, 400, 110), {
      collapsed: false,
      previewWidth: 400,
      expandedWidth: 400,
    });
    assert.deepEqual(resolveRightSidebarDragUpdate(1080, 1320, 220, 400, 110), {
      collapsed: false,
      previewWidth: 240,
      expandedWidth: 240,
    });
  });
});
