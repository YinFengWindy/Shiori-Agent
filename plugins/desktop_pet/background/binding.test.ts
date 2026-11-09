import assert from "node:assert/strict";
import test from "node:test";
import { readDesktopPetBinding } from "./binding";
const binding = { role_id: "role", provider: { plugin_id: "render", service_id: "models" }, model: { id: "m", display_name: "Model", body: { width: 300, height: 400 }, actions: ["wave"] } };
test("accepts a provider-neutral binding with no sprite fields", () => assert.deepEqual(readDesktopPetBinding({ binding }), binding));
test("distinguishes absent binding from malformed binding that must report failure", () => {
  assert.equal(readDesktopPetBinding({ binding: null }), null);
  assert.throws(() => readDesktopPetBinding({ binding: { ...binding, model: { ...binding.model, body: { width: -1, height: 400 } } } }), /无效/);
});
