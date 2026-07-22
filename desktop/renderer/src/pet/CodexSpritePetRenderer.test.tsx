/// <reference types="node" />

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CodexSpritePetRenderer } from "./CodexSpritePetRenderer";

test("desktop pet delegates dragging to Electron's native drag region", () => {
  const markup = renderToStaticMarkup(
    <CodexSpritePetRenderer spritesheetUrl="mira-asset://pet" state="idle" />,
  );
  const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

  assert.match(markup, /class="pet-drag-region"/);
  assert.match(styles, /\.pet-drag-region\s*\{[^}]*-webkit-app-region:\s*drag;/s);
});
