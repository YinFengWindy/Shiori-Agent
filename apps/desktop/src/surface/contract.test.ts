import assert from "node:assert/strict";
import { test } from "node:test";
import { desktopSurfaceWindowOptions } from "./contract.js";

test("surface construction stays hidden while retaining transparent window security", () => {
  const options = desktopSurfaceWindowOptions({ body: { width: 192, height: 208 } }, "preload.js");
  assert.equal(options.show, false);
  assert.equal(options.transparent, true);
  assert.equal(options.frame, false);
  assert.equal(options.alwaysOnTop, true);
  assert.equal(options.webPreferences.contextIsolation, true);
  assert.equal(options.webPreferences.nodeIntegration, false);
});
