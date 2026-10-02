import assert from "node:assert/strict";
import { test } from "node:test";
import { surfaceKeyFromSearch, surfaceQueryString } from "./entry.js";

test("a surface key round-trips through the window query string", () => {
  const key = { pluginId: "demo", surfaceId: "main" };
  assert.deepEqual(surfaceKeyFromSearch(surfaceQueryString(key)), key);
});

test("ids needing escaping survive the round trip", () => {
  const key = { pluginId: "a b&c", surfaceId: "x=y" };
  assert.deepEqual(surfaceKeyFromSearch(surfaceQueryString(key)), key);
});

test("a half-specified location yields no key rather than a partial one", () => {
  assert.equal(surfaceKeyFromSearch(""), null);
  assert.equal(surfaceKeyFromSearch("?plugin=demo"), null);
  assert.equal(surfaceKeyFromSearch("?surface=main"), null);
  assert.equal(surfaceKeyFromSearch("?plugin=&surface=main"), null);
});
