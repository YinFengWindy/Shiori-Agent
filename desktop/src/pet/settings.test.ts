import assert from "node:assert/strict";
import test from "node:test";
import { normalizeDesktopPetSettings } from "./settings.js";

test("desktop-pet settings disable incomplete bindings and retain valid positions", () => {
  assert.deepEqual(normalizeDesktopPetSettings({ enabled: true, roleId: "role-1", positions: { broken: { x: 1, y: 2 } } }), {
    enabled: false,
    roleId: "role-1",
    packageId: null,
    positions: { broken: { x: 1, y: 2 } },
  });
});
