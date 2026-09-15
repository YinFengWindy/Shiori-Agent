import assert from "node:assert/strict";
import test from "node:test";
import {
  desktopPetPresenceChanged,
  desktopPetSurfaceKey,
  isDesktopPetWindow,
  noDesktopPetPresence,
  readDesktopPetPresence,
} from "./desktopPet.js";
import type { SurfaceKey } from "../surface/host.js";

// The half of this coupling that pins the host's copy of the pet's identity
// and event names against the plugin's own lives in
// `plugins/desktop_pet/background/hostContract.test.ts`. It cannot live here:
// this file is in the *main-process* tsc program (`tsconfig.main.json`), which
// has no DOM lib and a `rootDir` of `src/`, and the plugin is renderer code.

test("presence reads the three fields the host needs out of the pet's stored blob", () => {
  assert.deepEqual(
    readDesktopPetPresence({ visible: true, roleId: "mira", packageId: "pet-1", positions: {} }),
    { visible: true, roleId: "mira" },
  );
});

test("a pet with no package is not visible, whatever the stored flag says", () => {
  assert.deepEqual(
    readDesktopPetPresence({ visible: true, roleId: "mira", packageId: null }),
    { visible: false, roleId: "mira" },
  );
});

test("anything the host cannot read as pet settings degrades to no pet", () => {
  for (const value of [null, undefined, "nope", 7, [], {}, { visible: true }]) {
    assert.deepEqual(readDesktopPetPresence(value), noDesktopPetPresence, JSON.stringify(value ?? null));
  }
});

test("visible is only believed when there is something to show", () => {
  // The plugin normalizes this too, but the host must not depend on that: it
  // reads the file the plugin wrote, and a hand-edited one would otherwise
  // leave the tray offering to hide a pet that cannot exist.
  assert.equal(readDesktopPetPresence({ visible: true, roleId: "mira", packageId: "" }).visible, false);
});

test("only the pet's own surface window is attributed to the pet", () => {
  const keys = new Map<number, SurfaceKey>([
    [1, desktopPetSurfaceKey],
    [2, { pluginId: "novelai", surfaceId: "pet" }],
    [3, { pluginId: "desktop_pet", surfaceId: "other" }],
  ]);
  const surfaces = { keyForWindowId: (id: number | null | undefined) => keys.get(id ?? -1) ?? null };

  assert.equal(isDesktopPetWindow(surfaces, { id: 1 }), true);
  // Another plugin naming its surface "pet" must not inherit voice channels.
  assert.equal(isDesktopPetWindow(surfaces, { id: 2 }), false);
  assert.equal(isDesktopPetWindow(surfaces, { id: 3 }), false);
  assert.equal(isDesktopPetWindow(surfaces, { id: 4 }), false);
  assert.equal(isDesktopPetWindow(surfaces, null), false);
});

test("a remembered position is not a presence change, so it triggers nothing", () => {
  // The plugin writes its settings on every drag, glide and role-requested
  // move. These writes must not interrupt the current voice turn.
  const before = readDesktopPetPresence({ visible: true, roleId: "mira", packageId: "pet-1", positions: {} });
  const afterDrag = readDesktopPetPresence({
    visible: true,
    roleId: "mira",
    packageId: "pet-1",
    positions: { "mira:display-1": { x: 10, y: 20 } },
  });

  assert.equal(desktopPetPresenceChanged(before, afterDrag), false);
});

test("every field the host reacts to counts as a change", () => {
  const base = { visible: true, roleId: "mira" };

  assert.equal(desktopPetPresenceChanged(base, { ...base, visible: false }), true);
  assert.equal(desktopPetPresenceChanged(base, { ...base, roleId: "other" }), true);
  assert.equal(desktopPetPresenceChanged(base, { ...base }), false);
});
