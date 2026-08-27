import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const mainSource = await readFile(new URL("./main.ts", import.meta.url), "utf-8");

test("desktop pet visibility changes refresh tray and voice state", () => {
  const refreshStart = mainSource.indexOf("function syncDesktopPetRuntimeState");
  const refreshEnd = mainSource.indexOf("\n}", refreshStart);
  assert.notEqual(refreshStart, -1, "desktop pet runtime refresh must exist");
  assert.notEqual(refreshEnd, -1, "desktop pet runtime refresh must have a body");
  const refreshSource = mainSource.slice(refreshStart, refreshEnd);

  assert.match(refreshSource, /desktopTray\?\.refresh\(\)/);
  assert.match(refreshSource, /syncVoiceAvailability\(\)/);
  assert.match(mainSource, /onPetVisibilityChanged:\s*syncDesktopPetRuntimeState/);
});
