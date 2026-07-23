import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("desktop pet uses the normal always-on-top level instead of the screen-saver level", () => {
  const source = readFileSync(new URL("./window.ts", import.meta.url), "utf8");

  assert.match(source, /show:\s*false,/);
  assert.match(source, /alwaysOnTop:\s*true,/);
  assert.doesNotMatch(source, /setAlwaysOnTop\(true,\s*["']screen-saver["']\)/);
});
