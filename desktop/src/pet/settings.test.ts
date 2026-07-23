import assert from "node:assert/strict";
import test from "node:test";
import { bindDesktopPetSettings, normalizeDesktopPetSettings } from "./settings.js";

test("desktop-pet settings disable incomplete bindings and retain valid positions", () => {
  assert.deepEqual(normalizeDesktopPetSettings({ enabled: true, roleId: "role-1", positions: { broken: { x: 1, y: 2 } } }), {
    visible: false,
    observationEnabled: false,
    roleId: "role-1",
    packageId: null,
    positions: { broken: { x: 1, y: 2 } },
  });
});

test("binding a saved role retains tray visibility independently", () => {
  const current = normalizeDesktopPetSettings({
    visible: false,
    observationEnabled: false,
    roleId: "role-a",
    packageId: "pet-a",
    positions: { "role-a:1": { x: 10, y: 20 } },
  });

  const activated = bindDesktopPetSettings(current, {
    roleId: "role-b",
    package: { id: "pet-b", displayName: "Pet B", spritesheetUrl: "mira-asset://pet-b" },
  }, false);

  assert.deepEqual(activated, {
    visible: false,
    observationEnabled: false,
    roleId: "role-b",
    packageId: "pet-b",
    positions: { "role-a:1": { x: 10, y: 20 } },
  });
});

test("changing the pet binding clears observation consent", () => {
  const current = normalizeDesktopPetSettings({
    visible: true,
    observationEnabled: true,
    roleId: "role-a",
    packageId: "pet-a",
  });

  const changed = bindDesktopPetSettings(current, {
    roleId: "role-b",
    package: { id: "pet-b", displayName: "Pet B", spritesheetUrl: "mira-asset://pet-b" },
  }, true);

  assert.equal(changed.observationEnabled, false);
});

test("reloading the same pet binding retains observation consent", () => {
  const current = normalizeDesktopPetSettings({
    visible: false,
    observationEnabled: true,
    roleId: "role-a",
    packageId: "pet-a",
  });

  const rebound = bindDesktopPetSettings(current, {
    roleId: "role-a",
    package: { id: "pet-a", displayName: "Pet A", spritesheetUrl: "mira-asset://pet-a" },
  }, true);

  assert.equal(rebound.observationEnabled, true);
});
