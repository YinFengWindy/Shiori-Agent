/// <reference types="node" />

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CodexSpritePetRenderer } from "./CodexSpritePetRenderer";

test("desktop pet keeps renderer pointer handling and the Codex grab cursor", () => {
  const markup = renderToStaticMarkup(
    <CodexSpritePetRenderer spritesheetUrl="mira-asset://pet" state="idle" />,
  );
  const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

  assert.match(markup, /class="pet-drag-region"/);
  assert.match(styles, /\.pet-drag-region\s*\{[^}]*cursor:\s*grab;/s);
  assert.match(styles, /\.pet-drag-region:active\s*\{[^}]*cursor:\s*grabbing;/s);
  assert.match(styles, /\.pet-dragging\s*\{[^}]*transform:\s*scale\(0\.95\);/s);
  assert.doesNotMatch(styles, /-webkit-app-region:\s*drag/);
});
