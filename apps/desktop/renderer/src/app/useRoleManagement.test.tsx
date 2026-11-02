import assert from "node:assert/strict";
import { test } from "node:test";
import { act, useRef, useState } from "react";
import { useLatestRef, type RoleRecord } from "@yinfengwindy/shiori-sdk";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { createRoleFormFromRole, isRoleFormDirty } from "../roles/roleFormState";
import { pluginRoleSettingsRegistry } from "../plugins/pluginFeatureRegistry";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";
import { proactiveRoleSettings } from "../../../../../plugins/proactive/ui/roleSettings";
import { readRoleProactiveForm } from "../../../../../plugins/proactive/ui/roleProactiveDefaults";
import { desktopPetRoleSettings } from "../../../../../plugins/desktop_pet/ui/roleSettings";
import type { RoleFormState } from "../shared/types";
import { useRoleManagement } from "./useRoleManagement";

function role(id: string): RoleRecord {
  return { id, name: id, description: "", system_prompt: "prompt", runtime_config: {},
    avatar: null, avatar_abs: null, chat_background: null, chat_background_abs: null,
    illustrations: [], illustrations_abs: [], asset_categories: [], asset_category_bindings: {},
    created_at: "", updated_at: "", plugin_state: { proactive: readRoleProactiveForm({}), desktop_pet: { enabled: false } } };
}

async function fixture(enablePet = false) {
  const stored = new Map([role("mira"), role("other")].map((value) => [value.id, value]));
  let fail = true;
  let delay: Promise<void> | undefined;
  let release = () => {};
  let selectOther = () => {};
  let save = async () => {};
  let refreshFails = false;
  let petVisible = false;
  const messages: string[] = [];
  const imports: string[] = [];
  const invoke = async ({ method, payload = {} }: { method: string; payload?: Record<string, unknown> }) => {
    if (method === "plugins.communication.open") return { payload: { generation: "test" } };
    if (method === "plugins.communication.close") return { payload: {} };
    if (method === "plugins.communication.call" && payload.target === "desktop_pet") {
      const enabled = stored.get("mira")?.plugin_state?.desktop_pet.enabled === true;
      if (!enabled) petVisible = false;
      else if ((payload.payload as Record<string, unknown>).forceVisible === true) petVisible = true;
      return { payload: {} };
    }
    const current = stored.get(String(payload.role_id));
    assert.ok(current);
    if (method === "roles.update") {
      assert.equal("proactive" in payload, false);
      const drafts = payload.plugin_drafts as Record<string, Record<string, unknown>>;
      assert.equal("proactive" in drafts, false);
      const sources = payload.illustration_sources as string[];
      imports.push(...sources);
      const updated = { ...current, name: String(payload.name), illustrations: [...current.illustrations, ...sources], plugin_state: { ...current.plugin_state, ...drafts } };
      stored.set(current.id, updated);
      return { payload: { role: updated } };
    }
    assert.equal(method, "plugin.proactive.settings_set");
    if (delay) await delay;
    if (fail) return { error: { message: "主动推送设置保存失败", code: "invalid_settings" }, payload: {} };
    stored.set(current.id, { ...stored.get(current.id)!, plugin_state: { ...current.plugin_state, proactive: { ...current.plugin_state?.proactive, ...payload.values as Record<string, unknown> } } });
    return { payload: stored.get(current.id)!.plugin_state!.proactive };
  };
  function Harness() {
    const [roles, setRoles] = useState([...stored.values()]);
    const [id, setId] = useState("mira");
    const current = roles.find((value) => value.id === id)!;
    const [form, setForm] = useState<RoleFormState>(() => ({ ...createRoleFormFromRole(current), name: "edited", illustrationSources: ["picture.png"], pluginSettings: { proactive: readRoleProactiveForm({ proactiveEnabled: true }), desktop_pet: { enabled: enablePet } } }));
    const [saving, setSaving] = useState(false);
    const formRef = useLatestRef(form);
    const request = useRef(0);
    const actions = useRoleManagement({
      activeRoleId: id, detailRoleId: id, detailRole: current, activeIllustration: "", selectedAvatarAsset: "", selectedChatBackground: "",
      roleFormRef: formRef, setSavingRole: setSaving, setSavingRoleAssets: () => {}, setDeletingRole: () => {}, setPendingRoleCardAction: () => {},
      feedback: { error: (message) => messages.push(message), success: (message) => messages.push(message), info: () => {}, warning: () => {} },
      setRoles, setActiveRoleId: () => {}, setSelectedAvatarAsset: () => {}, setSelectedChatBackground: () => {}, setActiveIllustration: () => {},
      updateRoleForm: setForm, openRoleWorkspace: () => {}, buildNavigationEntry: () => ({ view: { kind: "roles-list" }, activeRoleId: "mira", settingsSection: "general", settingsSubsection: "" }), replaceNavigationEntry: () => {},
      loadRolesFromBridge: async () => { if (refreshFails) throw new Error("offline"); const next = [...stored.values()]; setRoles(next); return next; },
      openRole: async (_id, updated) => { if (updated) setForm(createRoleFormFromRole(updated)); return true; },
      applyRoleSnapshot: () => {}, commitActiveSession: () => {}, removeCachedRoleSession: () => {}, rememberIllustration: async () => {}, roleAssetSaveRequestIdRef: request,
    });
    save = actions.saveRole;
    selectOther = () => { setId("other"); setForm(createRoleFormFromRole(stored.get("other")!)); };
    return <div data-id={id} data-saving={saving} data-dirty={isRoleFormDirty(form, current)} data-name={form.name} data-sources={form.illustrationSources.length} data-enabled={String(form.pluginSettings.proactive.proactiveEnabled)}>
      <button onClick={() => setForm(createRoleFormFromRole(current))}>reset</button>
    </div>;
  }
  pluginRoleSettingsRegistry.register({ pluginId: "proactive", ...proactiveRoleSettings });
  pluginRoleSettingsRegistry.register({ pluginId: "desktop_pet", ...desktopPetRoleSettings });
  setPluginEnabledSnapshot(["proactive", "desktop_pet"].map((id) => ({ id, enabled: true, state: "ACTIVE" })));
  const view = await mountTestComponent(<Harness />, { windowGlobals: { miraDesktop: { invoke, onEvent: () => () => {} } } });
  return { view, stored, imports, messages, save: () => save(), selectOther: () => selectOther(),
    succeed: () => { fail = false; }, failRefresh: () => { refreshFails = true; },
    pause: () => { delay = new Promise<void>((resolve) => { release = resolve; }); }, release: () => release(),
    petVisible: () => petVisible, hidePet: () => { petVisible = false; },
    state: () => view.container.firstElementChild as HTMLElement,
    async close() { await view.cleanup(); pluginRoleSettingsRegistry.unregister("proactive"); pluginRoleSettingsRegistry.unregister("desktop_pet"); resetPluginEnabledStateForTests(); },
  };
}

test("failed plugin save keeps its draft dirty and retries without replaying committed assets", async () => {
  const f = await fixture();
  try {
    await act(async () => f.save());
    assert.equal(f.stored.get("mira")?.name, "edited");
    assert.equal(f.state().dataset.enabled, "true");
    assert.equal(f.state().dataset.dirty, "true");
    assert.equal(f.state().dataset.saving, "false");
    assert.equal(f.state().dataset.sources, "0");
    assert.match(f.messages.at(-1)!, /角色已保存，插件设置未保存/);
    f.succeed();
    await act(async () => f.save());
    assert.deepEqual(f.imports, ["picture.png"]);
    assert.equal(f.stored.get("mira")?.plugin_state?.proactive.proactiveEnabled, true);
    assert.equal(f.state().dataset.dirty, "false");
  } finally { await f.close(); }
});

test("a committed pet setting takes effect despite a later RPC failure and is not replayed on retry", async () => {
  const f = await fixture(true);
  try {
    await act(async () => f.save());
    assert.equal(f.stored.get("mira")?.plugin_state?.desktop_pet.enabled, true);
    assert.equal(f.stored.get("mira")?.plugin_state?.proactive.proactiveEnabled, false);
    assert.equal(f.petVisible(), true);
    f.hidePet();
    f.succeed();
    await act(async () => f.save());
    assert.equal(f.stored.get("mira")?.plugin_state?.proactive.proactiveEnabled, true);
    assert.equal(f.petVisible(), false, "retry must respect the pet hidden after its committed save");
  } finally { await f.close(); }
});

test("reset after partial save uses the committed core baseline even when refresh fails", async () => {
  const f = await fixture();
  try {
    f.failRefresh();
    await act(async () => f.save());
    assert.equal(f.state().dataset.saving, "false");
    await act(async () => f.state().querySelector("button")!.click());
    assert.equal(f.state().dataset.name, "edited");
    assert.equal(f.state().dataset.enabled, "false");
    assert.equal(f.state().dataset.dirty, "false");
  } finally { await f.close(); }
});

test("a plugin save finishing after a role switch cannot replace the new role draft", async () => {
  const f = await fixture();
  try {
    f.pause(); f.succeed();
    let saving: Promise<void>;
    await act(async () => { saving = f.save(); await Promise.resolve(); });
    await act(async () => f.selectOther());
    await act(async () => { f.release(); await saving!; });
    assert.equal(f.state().dataset.id, "other");
    assert.equal(f.state().dataset.name, "other");
    assert.equal(f.state().dataset.enabled, "false");
    assert.equal(f.state().dataset.dirty, "false");
  } finally { await f.close(); }
});


test("a refresh failure after plugin persistence reports saved data and keeps the new baseline", async () => {
  const f = await fixture();
  try {
    f.succeed(); f.failRefresh();
    await act(async () => f.save());
    assert.equal(f.stored.get("mira")?.plugin_state?.proactive.proactiveEnabled, true);
    assert.equal(f.state().dataset.saving, "false");
    assert.equal(f.state().dataset.dirty, "false");
    assert.match(f.messages.at(-1)!, /角色及插件设置已保存/);
    assert.doesNotMatch(f.messages.at(-1)!, /未保存/);
    await act(async () => f.state().querySelector("button")!.click());
    assert.equal(f.state().dataset.enabled, "true");
  } finally { await f.close(); }
});
