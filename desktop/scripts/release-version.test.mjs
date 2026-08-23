import assert from "node:assert/strict";
import test from "node:test";
import { resolveReleaseVersion } from "./release-version.mjs";

test("resolveReleaseVersion accepts semver values from release tags", () => {
  assert.equal(resolveReleaseVersion("0.2.0"), "0.2.0");
  assert.equal(resolveReleaseVersion(" 1.0.0-beta.1 "), "1.0.0-beta.1");
});

test("resolveReleaseVersion leaves manual builds on package.json version", () => {
  assert.equal(resolveReleaseVersion(""), undefined);
  assert.throws(() => resolveReleaseVersion("release-1"), /Invalid release version/);
});
