import { createPluginRpcClient } from "../../../apps/desktop/renderer/src/plugins/pluginBridgeClient";
import assert from "node:assert/strict";
import test from "node:test";
import {
  openPetContextMenu,
  petContextMenuItems,
  petMenuHidePetId,
  petMenuMainWindowId,
} from "./petMenu";
import type { SurfaceHandle } from "../../../apps/desktop/renderer/src/surface/pluginSurfaceRegistry";

function fakeSurface(choice: string | null) {
  const calls: string[] = [];
  let requestedItems: { id: string; label: string }[] = [];
  const surface = {
    showContextMenu: async (items: { id: string; label: string }[]) => {
      requestedItems = items;
      calls.push("showContextMenu");
      return choice;
    },
    activateMainWindow: () => { calls.push("activateMainWindow"); },
  } as unknown as SurfaceHandle;
  return { surface, calls, get items() { return requestedItems; } };
}

function fakeHost(calls: string[]) {
  return {
    ...createPluginRpcClient("desktop_pet"),
    background: { call: async <T,>(_name: string, payload?: Record<string, unknown>) => {
      calls.push(`sync:${String(payload?.forceVisible)}`);
      return undefined as T;
    } },
  };
}

test("the plugin owns the menu items, not the host", () => {
  assert.deepEqual(petContextMenuItems.map((item) => item.id), [
    petMenuMainWindowId,
    petMenuHidePetId,
  ]);
  assert.deepEqual(petContextMenuItems.map((item) => item.label), ["显示主窗口", "隐藏桌宠"]);
});

test("choosing the main window entry pulls the main window forward", async () => {
  const surface = fakeSurface(petMenuMainWindowId);
  const hostCalls: string[] = [];

  await openPetContextMenu(surface.surface, fakeHost(hostCalls));

  assert.deepEqual(surface.calls, ["showContextMenu", "activateMainWindow"]);
  assert.deepEqual(hostCalls, []);
});

test("choosing the hide entry hides the pet through the host", async () => {
  const surface = fakeSurface(petMenuHidePetId);
  const hostCalls: string[] = [];

  await openPetContextMenu(surface.surface, fakeHost(hostCalls));

  assert.deepEqual(surface.calls, ["showContextMenu"]);
  assert.deepEqual(hostCalls, ["sync:false"]);
});

test("dismissing the menu without choosing does nothing and still settles", async () => {
  const surface = fakeSurface(null);
  const hostCalls: string[] = [];

  // Resolving rather than hanging is the point: Electron reports a dismissal
  // only via `menu-will-close`, so an await here must still finish.
  await openPetContextMenu(surface.surface, fakeHost(hostCalls));

  assert.deepEqual(surface.calls, ["showContextMenu"]);
  assert.deepEqual(hostCalls, []);
});

test("the menu is requested with a copy, so the shared item list cannot be mutated", async () => {
  const surface = fakeSurface(null);
  await openPetContextMenu(surface.surface, fakeHost([]));

  assert.deepEqual(surface.items, petContextMenuItems);
  assert.notEqual(surface.items[0], petContextMenuItems[0]);
});
