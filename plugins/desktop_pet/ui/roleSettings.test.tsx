import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { createFakePluginClient, mountTestComponent } from "@shiori/sdk/testing";
import { DesktopPetRoleSettings, desktopPetRoleSettings } from "./roleSettings";

test("pet toggle edits only its draft and gates enablement on selected packages", async () => {
  const changes: unknown[] = [];
  const synced: unknown[] = [];
  const view = await mountTestComponent(null);
  try {
    await view.render(<DesktopPetRoleSettings values={{ enabled: false }} snapshot={{ available: false }} onChange={(values) => changes.push(values)} />);
    let toggle = view.container.querySelector<HTMLButtonElement>('[aria-label="桌宠"]');
    assert.ok(toggle?.disabled);
    await view.render(<DesktopPetRoleSettings values={{ enabled: false }} snapshot={{ available: true }} onChange={(values) => changes.push(values)} />);
    toggle = view.container.querySelector<HTMLButtonElement>('[aria-label="桌宠"]');
    assert.ok(toggle && !toggle.disabled);
    await act(async () => { toggle.click(); });
    assert.deepEqual(changes, [{ enabled: true }]);
    assert.equal(synced.length, 0);
    await desktopPetRoleSettings.afterSave?.({ enabled: true }, createFakePluginClient({ background: { call: async <T,>(_name: string, payload?: Record<string, unknown>) => { synced.push(payload?.forceVisible); return undefined as T; } } }));
    assert.deepEqual(synced, [true]);
  } finally { await view.cleanup(); }
});
