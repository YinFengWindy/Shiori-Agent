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
      reply={{ paused: false, text: "", persistent: false }}
      bubbleLayout={{ placement: "below", height: 0 }}
    />,
  );
  const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

  assert.match(markup, /class="pet-drag-region"/);
  assert.match(styles, /\.pet-drag-region\s*\{[^}]*cursor:\s*grab;/s);
  assert.match(styles, /\.pet-drag-region:active\s*\{[^}]*cursor:\s*grabbing;/s);
  assert.match(styles, /\.pet-dragging\s*\{[^}]*transform:\s*scale\(0\.95\);/s);
  assert.doesNotMatch(styles, /-webkit-app-region:\s*drag/);
  assert.doesNotMatch(markup, /屏幕观察/);
  assert.doesNotMatch(styles, /pet-reply-toggle/);
});

test("persistent reply bubbles expose a dismiss control", () => {
  const markup = renderToStaticMarkup(
    <CodexSpritePetRenderer
      spritesheetUrl="mira-asset://pet"
      state="idle"
      reply={{ paused: true, text: "Windows 已锁定", persistent: true }}
      bubbleLayout={{ placement: "below", height: 80 }}
    />,
  );

  assert.match(markup, /aria-label="关闭消息"/);
});

test("transient reply bubbles do not expose a dismiss control", () => {
  const markup = renderToStaticMarkup(
    <CodexSpritePetRenderer
      spritesheetUrl="mira-asset://pet"
      state="idle"
      reply={{ paused: false, text: "继续写吧", persistent: false }}
      bubbleLayout={{ placement: "below", height: 80 }}
    />,
  );

  assert.match(markup, /继续写吧/);
  assert.match(markup, /pet-bubble-below/);
  assert.doesNotMatch(markup, /aria-label="关闭消息"/);
  assert.doesNotMatch(markup, /屏幕观察/);
});

test("above reply bubbles render ahead of the sprite", () => {
  const markup = renderToStaticMarkup(
    <CodexSpritePetRenderer
      spritesheetUrl="mira-asset://pet"
      state="idle"
      reply={{ paused: false, text: "继续写吧", persistent: false }}
      bubbleLayout={{ placement: "above", height: 80 }}
    />,
  );
  const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

  assert.match(markup, /pet-bubble-above/);
  assert.ok(markup.indexOf('class="pet-bubble"') < markup.indexOf('class="pet-drag-region"'));
  assert.match(styles, /\.pet-bubble-above\s*\{[^}]*flex-direction:\s*column;/s);
  assert.doesNotMatch(styles, /\.pet-bubble-above\s*\{[^}]*column-reverse/s);
});

test("oversized reply bubbles keep their full text in a scrollable surface", () => {
  renderToStaticMarkup(
    <CodexSpritePetRenderer
      spritesheetUrl="mira-asset://pet"
      state="idle"
      reply={{ paused: false, text: "很长的完整回复", persistent: false }}
      bubbleLayout={{ placement: "above", height: 80 }}
    />,
  );
  const styles = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

  assert.match(styles, /\.pet-bubble\s*\{[^}]*overflow-y:\s*auto;/s);
  assert.match(styles, /scrollbar-width:\s*none/);
});
