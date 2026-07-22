import assert from "node:assert/strict";
import test from "node:test";
import { activateDesktopPetSettings, normalizeDesktopPetSettings } from "./settings.js";

test("desktop-pet settings disable incomplete bindings and retain valid positions", () => {
  assert.deepEqual(normalizeDesktopPetSettings({ enabled: true, roleId: "role-1", positions: { broken: { x: 1, y: 2 } } }), {
    enabled: false,
    roleId: "role-1",
    packageId: null,
    positions: { broken: { x: 1, y: 2 } },
  });
});

test("activating a role replaces the single desktop-pet slot", () => {
  const current = normalizeDesktopPetSettings({
    enabled: true,
    roleId: "role-a",
    packageId: "pet-a",
    positions: { "role-a:1": { x: 10, y: 20 } },
  });

  const activated = activateDesktopPetSettings(current, {
    roleId: "role-b",
    package: { id: "pet-b", displayName: "Pet B", spritesheetUrl: "mira-asset://pet-b" },
  });

  assert.deepEqual(activated, {
    enabled: true,
    roleId: "role-b",
    packageId: "pet-b",
    positions: { "role-a:1": { x: 10, y: 20 } },
  });
});
