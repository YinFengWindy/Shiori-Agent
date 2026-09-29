/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryGlyph } from "./StoryGlyph";

describe("StoryGlyph", () => {
  it("plays the flutter motion on its motif", () => {
    assert.match(renderToStaticMarkup(<StoryGlyph />), /nav-glyph-motif--flutter/);
  });
});
