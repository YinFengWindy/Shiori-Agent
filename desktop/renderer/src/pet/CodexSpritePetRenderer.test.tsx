/// <reference types="node" />

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { CodexSpritePetRenderer } from "./CodexSpritePetRenderer";

test("desktop pet keeps renderer pointer handling and the Codex grab cursor", () => {
  const markup = renderToStaticMarkup(
    <CodexSpritePetRenderer
      spritesheetUrl="mira-asset://pet"
      state="idle"
      observation={{ status: "off", enabled: false, bubble: "", persistent: false }}
    />,
  );
  const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");
  const interactions = readFileSync(new URL("./useCodexPetInteraction.ts", import.meta.url), "utf8");

  assert.match(markup, /class="pet-drag-region"/);
  assert.match(styles, /\.pet-drag-region\s*\{[^}]*cursor:\s*grab;/s);
  assert.match(styles, /\.pet-drag-region:active\s*\{[^}]*cursor:\s*grabbing;/s);
  assert.match(styles, /\.pet-dragging\s*\{[^}]*transform:\s*scale\(0\.95\);/s);
  assert.doesNotMatch(styles, /-webkit-app-region:\s*drag/);
  assert.match(interactions, /function onDoubleClick\(\): void/);
  assert.match(interactions, /pointerHandlers:\s*\{[^}]*onDoubleClick/s);
  assert.doesNotMatch(interactions, /function onClick\(\): void/);
});

test("persistent observation failures expose a dismiss control", () => {
  const markup = renderToStaticMarkup(
    <CodexSpritePetRenderer
      spritesheetUrl="mira-asset://pet"
      state="idle"
      observation={{ status: "failed", enabled: true, bubble: "观察失败", persistent: true }}
    />,
  );

  assert.match(markup, /aria-label="关闭消息"/);
  assert.match(markup, /pet-observation-failed/);
});

test("transient observation bubbles do not expose a dismiss control", () => {
  const markup = renderToStaticMarkup(
    <CodexSpritePetRenderer
      spritesheetUrl="mira-asset://pet"
      state="idle"
      observation={{ status: "observing", enabled: true, bubble: "继续写吧", persistent: false }}
    />,
  );

  assert.match(markup, /继续写吧/);
  assert.doesNotMatch(markup, /aria-label="关闭消息"/);
  assert.match(markup, /aria-label="关闭屏幕观察"/);
});
