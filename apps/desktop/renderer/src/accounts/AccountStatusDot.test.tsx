import assert from "node:assert/strict";
import { test } from "node:test";
import { accountStatusDotTone } from "./AccountStatusDot";

test("status dot is green online, yellow while connecting or awaiting login, red on error, gray otherwise", () => {
  assert.equal(accountStatusDotTone({ runtimeActive: true, connection: "online" }), "bg-success");
  assert.equal(accountStatusDotTone({ runtimeActive: true, connection: "connecting" }), "bg-warning");
  assert.equal(accountStatusDotTone({ runtimeActive: true, connection: "login_required" }), "bg-warning");
  assert.equal(accountStatusDotTone({ runtimeActive: true, connection: "error" }), "bg-danger");
  assert.equal(accountStatusDotTone({ runtimeActive: true, connection: "unknown" }), "bg-ink-faint");
  // A plugin that is not running cannot vouch for an online account.
  assert.equal(accountStatusDotTone({ runtimeActive: false, connection: "online" }), "bg-ink-faint");
});
