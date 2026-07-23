import assert from "node:assert/strict";
import test from "node:test";
import { selectPrimaryDisplaySource } from "./primaryDisplay.js";
import { PrimaryDisplayUnavailableError } from "./types.js";

test("primary display capture resolves only the matching display source", () => {
  const primary = { display_id: "2", name: "primary" };
  const secondary = { display_id: "1", name: "secondary" };

  assert.equal(selectPrimaryDisplaySource(2, [secondary, primary]), primary);
  assert.throws(
    () => selectPrimaryDisplaySource(3, [secondary, primary]),
    PrimaryDisplayUnavailableError,
  );
});
