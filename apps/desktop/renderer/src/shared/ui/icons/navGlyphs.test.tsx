/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { ChatsGlyph, RolesGlyph, SearchGlyph, SettingsGlyph, StoryGlyph } from "./navGlyphs.js";

const plainSearchBody = renderToStaticMarkup(<MagnifyingGlass size={256} weight="regular" />);

describe("nav glyphs", () => {
  it("keep the untouched Phosphor regular glyph and add one animatable motif group", () => {
    const markup = renderToStaticMarkup(<SearchGlyph className="h-[19px] w-[19px]" />);
    assert.ok(markup.includes(plainSearchBody), "base glyph is Phosphor regular, unchanged");
    assert.equal(markup.match(/class="nav-glyph-motif /g)?.length, 1);
    assert.match(markup, /class="nav-glyph h-\[19px\] w-\[19px\]"/);
    assert.match(markup, /aria-hidden="true"/);
  });

  it("give every instance its own gradient id and point the active fill at it", () => {
    const markup = renderToStaticMarkup(<><ChatsGlyph /><ChatsGlyph /></>);
    const ids = [...markup.matchAll(/<linearGradient id="([^"]+)"/g)].map((match) => match[1]);
    assert.equal(ids.length, 2);
    assert.notEqual(ids[0], ids[1]);
    for (const id of ids) assert.ok(markup.includes(`--nav-motif-gradient:url(#${id})`));
  });

  it("tag each glyph with its motion", () => {
    const motions = [
      [SearchGlyph, "twinkle"],
      [ChatsGlyph, "beat"],
      [RolesGlyph, "wiggle"],
      [SettingsGlyph, "spin"],
      [StoryGlyph, "flutter"],
    ] as const;
    for (const [Glyph, motion] of motions) {
      assert.match(renderToStaticMarkup(<Glyph />), new RegExp(`nav-glyph-motif--${motion}`));
    }
  });
});
