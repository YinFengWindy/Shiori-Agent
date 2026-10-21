import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider, type PluginRoleValues } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { NovelAiRoleSettings, novelAiRoleSettings } from "./roleSettings";

// The role editor's draft bookkeeping (dirty check, explicit Save, dropping a
// disabled plugin's edits) is the host's, covered by pluginRoleSettings.test.ts;
// this checks what novelai contributes to it.

test("NovelAI CG preference is read from its own snapshot and never written into runtime_config", () => {
  // `storage: "plugin"` with no `write`: the role's runtime_config is never touched.
  assert.equal(novelAiRoleSettings.storage, "plugin");
  assert.equal("write" in novelAiRoleSettings, false);
  // No save of its own: the value only persists through the editor's explicit Save.
  assert.equal("afterSave" in novelAiRoleSettings, false);

  const snapshot = { autoSceneCgEnabled: false };
  assert.deepEqual(novelAiRoleSettings.read(snapshot), { autoSceneCgEnabled: false });
  assert.deepEqual(novelAiRoleSettings.read({ autoSceneCgEnabled: true, available: true }), { autoSceneCgEnabled: true });
  assert.deepEqual(novelAiRoleSettings.read({ autoSceneCgEnabled: "yes" }), { autoSceneCgEnabled: false }, "only a real true enables it");
  assert.deepEqual(snapshot, { autoSceneCgEnabled: false }, "reading leaves the snapshot as it was");
});

async function settleDialog() {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
}

test("CG prompt dialog saves on close, restores Chinese multiline instructions and never edits the role draft", async () => {
  const { host } = createFakeHostServices();
  const changes: unknown[] = [];
  const saves: unknown[] = [];
  let instructions = "";
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    if (method === "role_settings.set") { saves.push(payload); instructions = String(payload?.prompt_instructions); }
    else assert.equal(method, "role_settings.get");
    return { prompt_instructions: instructions } as T;
  } });
  const card = () => <PluginHostServicesProvider services={host}>
    <NovelAiRoleSettings roleId="mira" client={client} moodCatalog={[]} values={{ autoSceneCgEnabled: true }} onChange={(next) => changes.push(next)} />
  </PluginHostServicesProvider>;
  const view = await mountTestComponent(card());
  try {
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="自动场景 CG设置"]')!.click());
    await settleDialog();
    const dialog = document.querySelector<HTMLElement>('[role="dialog"]')!;
    assert.match(dialog.textContent ?? "", /补充要求/);
    await changeInputValue(dialog.querySelector<HTMLTextAreaElement>("textarea")!, "保留猫耳\n红色蝴蝶结");
    assert.equal(saves.length, 0);
    await act(async () => dialog.querySelector<HTMLButtonElement>('[aria-label="关闭"]')!.click());
    await settleDialog();
    assert.deepEqual(saves, [{ role_id: "mira", prompt_instructions: "保留猫耳\n红色蝴蝶结" }]);
    assert.deepEqual(changes, []);
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="自动场景 CG设置"]')!.click());
    await settleDialog();
    assert.equal(document.querySelector<HTMLTextAreaElement>('[role="dialog"] textarea')?.value, instructions);
  } finally { await view.cleanup(); }

  const again = await mountTestComponent(card());
  try {
    await act(async () => again.container.querySelector<HTMLButtonElement>('[aria-label="自动场景 CG设置"]')!.click());
    await settleDialog();
    const field = document.querySelector<HTMLTextAreaElement>('[role="dialog"] textarea')!;
    assert.equal(field.value, "保留猫耳\n红色蝴蝶结");
    await changeInputValue(field, "");
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 450)); });
    assert.equal(instructions, "", "clearing saves after the normal debounce");
  } finally { await again.cleanup(); }
});

test("CG prompt settings require a saved role and make no request for a new role", async () => {
  const { host } = createFakeHostServices();
  const client = createFakePluginClient({ call: async () => assert.fail("unsaved role must not load settings") });
  const view = await mountTestComponent(<PluginHostServicesProvider services={host}>
    <NovelAiRoleSettings roleId={null} client={client} moodCatalog={[]} values={{ autoSceneCgEnabled: false }} onChange={() => undefined} />
  </PluginHostServicesProvider>);
  try {
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="自动场景 CG设置"]')!.click());
    await settleDialog();
    assert.match(document.querySelector('[role="dialog"]')?.textContent ?? "", /请先保存角色/);
    assert.equal(document.querySelector('[role="dialog"] textarea'), null);
  } finally { await view.cleanup(); }
});

test("NovelAI CG toggle only edits the role draft", async () => {
  const changes: PluginRoleValues[] = [];
  const values = { autoSceneCgEnabled: false };
  const view = await mountTestComponent(<NovelAiRoleSettings roleId="role-1" client={createFakePluginClient()} moodCatalog={[]} values={values} onChange={(next) => changes.push(next)} />);
  try {
    const toggle = view.container.querySelector<HTMLButtonElement>('[aria-label="自动场景 CG"]');
    assert.equal(toggle?.getAttribute("aria-checked"), "false");
    await act(async () => { toggle?.click(); });
    assert.deepEqual(changes, [{ autoSceneCgEnabled: true }]);
    assert.deepEqual(values, { autoSceneCgEnabled: false }, "the edit is a new draft, not a mutation of the current one");
  } finally { await view.cleanup(); }
});
