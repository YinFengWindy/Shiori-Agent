import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { DesktopPetRoleSettings, desktopPetRoleSettings } from "./roleSettings";

test("pet toggle edits only its draft and gates enablement on selected packages", async () => {
  const changes: unknown[] = [];
  const synced: unknown[] = [];
  const view = await mountTestComponent(null);
  try {
    await view.render(<DesktopPetRoleSettings roleId="role-1" client={createFakePluginClient()} moodCatalog={[]} values={{ enabled: false }} snapshot={{ available: false }} onChange={(values) => changes.push(values)} />);
    let toggle = view.container.querySelector<HTMLButtonElement>('[aria-label="桌宠"]');
    assert.ok(toggle?.disabled);
    await view.render(<DesktopPetRoleSettings roleId="role-1" client={createFakePluginClient()} moodCatalog={[]} values={{ enabled: false }} snapshot={{ available: true }} onChange={(values) => changes.push(values)} />);
    toggle = view.container.querySelector<HTMLButtonElement>('[aria-label="桌宠"]');
    assert.ok(toggle && !toggle.disabled);
    await act(async () => { toggle.click(); });
    assert.deepEqual(changes, [{ enabled: true }]);
    assert.equal(synced.length, 0);
    await desktopPetRoleSettings.afterSave?.({ enabled: true }, createFakePluginClient({ background: { call: async <T,>(_name: string, payload?: Record<string, unknown>) => { synced.push(payload?.forceVisible); return undefined as T; } } }));
    assert.deepEqual(synced, [true]);
  } finally { await view.cleanup(); }
});

async function settle() {
  // Base UI finishes its open/close transition on later frames.
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
}

test("the ⚙ opens a 「桌宠」 dialog with 「直播陪伴」; closing submits the room at once and it shows again on reopen", async () => {
  const { host } = createFakeHostServices();
  const saves: unknown[] = [];
  let stored = { room_id: null as number | null, reply_interval_seconds: 5, wait_timeout_seconds: 30 };
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    if (method === "live.config.get") return structuredClone(stored) as T;
    if (method === "live.config.set") { saves.push(payload); stored = { ...stored, room_id: payload?.room_id as number }; return structuredClone(stored) as T; }
    if (method === "bilibili.account.status") return { state: "logged_out" } as T;
    if (method === "live.status") return { role_id: "role-1", state: "idle", connection: null, room: null, configured_room_id: stored.room_id, run_id: null, queue_length: 0, generating: false, output_pending: false, connection_error: "", reply_error: "", stop_reason: "", counters: {}, recent: [] } as T;
    throw new Error(`unexpected ${method}`);
  } });
  const changes: unknown[] = [];
  const card = () => <PluginHostServicesProvider services={host}>
    <DesktopPetRoleSettings roleId="role-1" client={client} moodCatalog={[]} values={{ enabled: true }} snapshot={{ enabled: true, available: true }} onChange={(values) => changes.push(values)} />
  </PluginHostServicesProvider>;
  const view = await mountTestComponent(card());
  const gear = () => view.container.querySelector<HTMLButtonElement>('button[aria-label="桌宠设置"]')!;
  const room = () => document.querySelector<HTMLInputElement>('[role="dialog"] [aria-label="直播间号"]')!;
  try {
    await act(async () => gear().click());
    await settle();
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
    assert.match(dialog.textContent ?? "", /^桌宠/);
    assert.ok(dialog.querySelector('section[aria-label="直播陪伴"]'));
    await changeInputValue(room(), "21452505");
    assert.equal(saves.length, 0);
    await act(async () => dialog.querySelector<HTMLButtonElement>('button[aria-label="关闭"]')!.click());
    await settle();
    assert.deepEqual(saves, [{ room_id: 21452505, reply_interval_seconds: 5, wait_timeout_seconds: 30, role_id: "role-1" }], "submitted on close");
    assert.deepEqual(changes, [], "the dialog never touches the role draft");

    await act(async () => gear().click());
    await settle();
    assert.equal(room().value, "21452505");
  } finally { await view.cleanup(); }

  // Entering the role again loads what was stored.
  const again = await mountTestComponent(card());
  try {
    await act(async () => again.container.querySelector<HTMLButtonElement>('button[aria-label="桌宠设置"]')!.click());
    await settle();
    assert.equal(room().value, "21452505");
  } finally { await again.cleanup(); }
});

test("a role not saved yet loads nothing and has nothing to configure", async () => {
  const { host } = createFakeHostServices();
  const client = createFakePluginClient({ call: async () => assert.fail("no request for an unsaved role") });
  const view = await mountTestComponent(<PluginHostServicesProvider services={host}>
    <DesktopPetRoleSettings roleId={null} client={client} moodCatalog={[]} values={{ enabled: false }} snapshot={{ available: false }} onChange={() => undefined} />
  </PluginHostServicesProvider>);
  try {
    await act(async () => view.container.querySelector<HTMLButtonElement>('button[aria-label="桌宠设置"]')!.click());
    await settle();
    assert.match(document.querySelector('[role="dialog"]')?.textContent ?? "", /请先保存角色/);
  } finally { await view.cleanup(); }
});
