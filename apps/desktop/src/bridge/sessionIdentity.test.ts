import assert from "node:assert/strict";
import test from "node:test";
import { roleIdFromSessionKey } from "./sessionIdentity.js";

test("only canonical nonempty role session keys identify a role", () => {
  assert.equal(roleIdFromSessionKey("role:mira"), "mira");
  for (const key of ["role:", "mira", "telegram:42", ""]) assert.equal(roleIdFromSessionKey(key), null);
});
