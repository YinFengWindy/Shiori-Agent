import assert from "node:assert/strict";
import test from "node:test";
import {
  desktopPetCommandMethod,
  desktopPetPluginId,
  desktopPetSurfaceKey,
  readDesktopPetPresence,
} from "../../../apps/desktop/src/pluginCoupling/desktopPet";
import petBackground, {
  desktopPetCommandMethod as pluginCommandMethod,
} from "./index";
import { desktopPetSurfaceId } from "./controller";
import { desktopPetBindingPatch, normalizeDesktopPetSettings } from "./settings";

/**
 * Pins the host's copy of the pet coupling to the plugin's.
 *
 * The two sides declare these strings separately on purpose — sharing them
 * would mean the host importing from a plugin — which leaves exactly one
 * failure mode: renaming one copy and not the other. Nothing would break at
 * build time; the role-settings sync command would simply stop working
 * at runtime, with no error anywhere. A test is the only thing that catches it,
 * and a test may import across a boundary that a dependency must not.
 *
 * It lives on the plugin side rather than next to `pluginCoupling/desktopPet.ts`
 * because that file is in the main-process tsc program, which has no DOM lib
 * and a `rootDir` of `apps/desktop/src` — it cannot reach renderer code at all.
 */

test("the host and the plugin agree on the pet's identity and event names", () => {
  assert.equal(desktopPetPluginId, petBackground.pluginId);
  assert.equal(desktopPetSurfaceKey.surfaceId, desktopPetSurfaceId);
  assert.equal(desktopPetCommandMethod, pluginCommandMethod);
});

test("the host reads the pet's presence out of what the plugin actually writes", () => {
  // The field *names* are the fragile part: `readDesktopPetPresence` picks
  // `visible` / `roleId` / `packageId` out of the plugin's private blob by
  // hand. Renaming one of them in `types.ts` would silently degrade the host
  // to "there is no pet" — tray entry permanently disabled, voice never
  // admitted, close policy changed — with nothing red and nothing logged.
  // Feeding the plugin's real output through the host's reader is what makes
  // that rename fail here instead.
  const binding = {
    roleId: "mira",
    package: { id: "pet-1", displayName: "Pet", spritesheetUrl: "shiori-asset://local/x" },
  };
  const bound = { ...normalizeDesktopPetSettings(null), ...desktopPetBindingPatch(binding, true) };

  assert.deepEqual(readDesktopPetPresence(bound), { visible: true, roleId: "mira" });
  assert.deepEqual(
    readDesktopPetPresence({ ...bound, ...desktopPetBindingPatch(binding, false) }),
    { visible: false, roleId: "mira" },
  );
  // A pet that never got a binding: what a fresh install stores.
  assert.deepEqual(
    readDesktopPetPresence(normalizeDesktopPetSettings(null)),
    { visible: false, roleId: null },
  );
});
