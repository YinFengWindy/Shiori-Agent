import assert from "node:assert/strict";
import test from "node:test";
import { desktopPetBindingPatch, normalizeDesktopPetSettings } from "./settings";
test("upgrades legacy selection and preserves explicit hidden state and positions", () => {
  const settings = normalizeDesktopPetSettings({ visible: false, roleId: "r", packageId: "m", positions: { "r:d": { x: 10, y: 20 }, invalid: { x: NaN, y: 0 } } });
  assert.deepEqual(settings, { visible: false, roleId: "r", model: { provider: { plugin_id: "pet_codex_sprite", service_id: "models" }, model_id: "m" }, positions: { "r:d": { x: 10, y: 20 } } });
});
test("selection patches cannot overwrite a position saved during a model load", () => {
  const patch = desktopPetBindingPatch({ role_id: "r", provider: { plugin_id: "p", service_id: "models" }, model: { id: "m", display_name: "M", body: { width: 10, height: 10 }, actions: [] } }, true);
  assert.equal("positions" in patch, false);
  assert.deepEqual(normalizeDesktopPetSettings(null), { visible: false, roleId: null, model: null, positions: {} });
});
