import assert from "node:assert/strict";
import { test } from "node:test";
import { act, useRef, useState } from "react";
import { useLatestRef, type RoleRecord, type PluginRoleSettingsContribution, type PluginRoleValues } from "@yinfengwindy/shiori-sdk";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { createRoleFormFromRole, isRoleFormDirty } from "../roles/roleFormState";
import { pluginRoleSettingsRegistry } from "../plugins/pluginFeatureRegistry";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";
import type { AppMainView, RoleFormState } from "../shared/types";
import { useRoleManagement } from "./useRoleManagement";
import { useRolePresentation } from "./useRolePresentation";
import { createDesktopRoleList } from "./desktopRoleList";

function readSampleValues(state: PluginRoleValues): PluginRoleValues {
  return { enabled: false, limit: 35, batchSize: 6, mode: "daily", ...state };
}

const sampleRoleSettings: PluginRoleSettingsContribution = {
  storage: "plugin", Component: () => null, read: readSampleValues,
  save: (roleId, values, previous, client) => client.call<PluginRoleValues>("settings_set", {
    role_id: roleId, values: Object.fromEntries(Object.entries(values).filter(([key, value]) => value !== previous[key])),
  }),
};
const secondaryRoleSettings: PluginRoleSettingsContribution = {
  storage: "plugin", Component: () => null, read: (state) => ({ enabled: state.enabled === true }),
  afterSave: (values, client) => client.background.call("sync", { activate: values.enabled === true }),
};

function role(id: string): RoleRecord {
  return { id, name: id, description: "", system_prompt: "prompt", runtime_config: {},
    avatar: null, avatar_abs: null, chat_background: null, chat_background_abs: null,
    illustrations: [], illustrations_abs: [], asset_categories: [], asset_category_bindings: {},
    created_at: "", updated_at: "", plugin_state: { sample: readSampleValues({}), secondary: { enabled: false } } };
}

async function fixture(enableSecondary = false) {
  const stored = new Map([role("mira"), role("other")].map((value) => [value.id, value]));
  let fail = true;
  let delay: Promise<void> | undefined;
  let release = () => {};
  let selectOther = () => {};
  let save = async () => {};
  let editSample: (values: Record<string, unknown>) => void = () => {};
  let refreshFails = false;
  let refreshRejected = false;
  let closeFails = false;
  let resourceActive = false;
  const messages: string[] = [];
  const imports: string[] = [];
  const invoke = async ({ method, payload = {} }: { method: string; payload?: Record<string, unknown> }) => {
    if (method === "plugins.communication.open") return { payload: { generation: "test" } };
    if (method === "plugins.communication.close") return closeFails
      ? { payload: {}, error: { code: "offline", message: "close failed" } } : { payload: {} };
    if (method === "roles.list") {
      if (refreshFails) throw new Error("offline");
      return refreshRejected ? { payload: {}, error: { code: "offline", message: "list failed" } }
        : { payload: { roles: [...stored.values()] } };
    }
    if (method === "plugins.communication.call" && payload.target === "secondary") {
      const enabled = stored.get("mira")?.plugin_state?.secondary.enabled === true;
      if (!enabled) resourceActive = false;
      else if ((payload.payload as Record<string, unknown>).activate === true) resourceActive = true;
      return { payload: {} };
    }
    const current = stored.get(String(payload.role_id));
    assert.ok(current);
    if (method === "roles.update") {
      assert.equal("sample" in payload, false);
      const drafts = payload.plugin_drafts as Record<string, Record<string, unknown>>;
      assert.equal("sample" in drafts, false);
      const sources = payload.illustration_sources as string[];
      imports.push(...sources);
      const updated = { ...current, name: String(payload.name), illustrations: [...current.illustrations, ...sources], plugin_state: { ...current.plugin_state, ...drafts } };
      stored.set(current.id, updated);
      return { payload: { role: updated } };
    }
    assert.equal(method, "sample.settings_set");
    if (delay) await delay;
    if (fail) return { error: { message: "示例设置保存失败", code: "invalid_settings" }, payload: {} };
    const latest = stored.get(current.id)!;
    stored.set(current.id, { ...latest, plugin_state: { ...latest.plugin_state, sample: { ...latest.plugin_state?.sample, ...payload.values as Record<string, unknown> } } });
    return { payload: stored.get(current.id)!.plugin_state!.sample };
  };
  function Harness() {
    const [roles, setRoles] = useState([...stored.values()]);
    const [id, setId] = useState("mira");
    const current = roles.find((value) => value.id === id)!;
    const [form, setForm] = useState<RoleFormState>(() => ({ ...createRoleFormFromRole(current), name: "edited", illustrationSources: ["picture.png"], pluginSettings: { sample: readSampleValues({ enabled: true }), secondary: { enabled: enableSecondary } } }));
    const [saving, setSaving] = useState(false);
    const formRef = useLatestRef(form);
    const activeRoleIdRef = useLatestRef(id);
    const mainViewRef = useLatestRef<AppMainView>({ kind: "role-detail", roleId: id });
    const request = useRef(0);
    const feedback = { error: (message: string) => messages.push(message), success: (message: string) => messages.push(message), info: () => {}, warning: () => {} };
    const presentation = useRolePresentation({ activeRoleIdRef, mainViewRef, roleFormRef: formRef,
      setActiveRoleId: setId, setActiveIllustration: () => {}, setSelectedAvatarAsset: () => {}, setSelectedChatBackground: () => {}, updateRoleForm: setForm });
    const roleList = createDesktopRoleList({ setRoles, setUnreadCounts: () => {}, feedback, retainCachedRoleSessions: () => {} });
    const actions = useRoleManagement({
      activeRoleId: id, detailRoleId: id, detailRole: current, activeIllustration: "", selectedAvatarAsset: "", selectedChatBackground: "",
      roleFormRef: formRef, setSavingRole: setSaving, setSavingRoleAssets: () => {}, setDeletingRole: () => {}, setPendingRoleCardAction: () => {},
      feedback,
      setRoles, setActiveRoleId: () => {}, setSelectedAvatarAsset: () => {}, setSelectedChatBackground: () => {}, setActiveIllustration: () => {},
      updateRoleForm: setForm, openRoleWorkspace: () => {}, buildNavigationEntry: () => ({ view: { kind: "roles-list" }, activeRoleId: "mira", settingsSection: "general", settingsSubsection: "" }), replaceNavigationEntry: () => {},
      loadRolesFromBridge: roleList.loadRolesFromBridge,
      openRole: async (_id, updated) => { if (updated) presentation.applyRoleSnapshot(updated); return true; },
      applyRoleSnapshot: presentation.applyRoleSnapshot, commitActiveSession: () => {}, removeCachedRoleSession: () => {}, rememberIllustration: async () => {}, roleAssetSaveRequestIdRef: request,
    });
    save = actions.saveRole;
    selectOther = () => { setId("other"); setForm(createRoleFormFromRole(stored.get("other")!)); };
    editSample = (values) => setForm((draft) => ({ ...draft, pluginSettings: { ...draft.pluginSettings, sample: { ...draft.pluginSettings.sample, ...values } } }));
    return <div data-id={id} data-saving={saving} data-dirty={isRoleFormDirty(form, current)} data-name={form.name} data-sources={form.illustrationSources.length} data-enabled={String(form.pluginSettings.sample.enabled)} data-max-steps={form.pluginSettings.sample.limit} data-content-limit={form.pluginSettings.sample.batchSize}>
      <button onClick={() => setForm(createRoleFormFromRole(current))}>reset</button>
    </div>;
  }
  pluginRoleSettingsRegistry.register({ pluginId: "sample", ...sampleRoleSettings });
  pluginRoleSettingsRegistry.register({ pluginId: "secondary", ...secondaryRoleSettings });
  setPluginEnabledSnapshot(["sample", "secondary"].map((id) => ({ id, enabled: true, state: "ACTIVE" })));
  const view = await mountTestComponent(<Harness />, { windowGlobals: { miraDesktop: { invoke, onEvent: () => () => {} } } });
  return { view, stored, imports, messages, save: () => save(), selectOther: () => selectOther(),
    succeed: () => { fail = false; }, failRefresh: () => { refreshFails = true; },
    rejectRefresh: () => { refreshRejected = true; }, failClose: () => { closeFails = true; },
    editSample: (values: Record<string, unknown>) => editSample(values),
    changeServerSettings(values: Record<string, unknown>) {
      const current = stored.get("mira")!;
      stored.set("mira", { ...current, plugin_state: { ...current.plugin_state, sample: { ...current.plugin_state?.sample, ...values } } });
    },
    pause: () => { delay = new Promise<void>((resolve) => { release = resolve; }); }, release: () => release(),
    resourceActive: () => resourceActive, deactivateResource: () => { resourceActive = false; },
    state: () => view.container.firstElementChild as HTMLElement,
    async close() { await view.cleanup(); pluginRoleSettingsRegistry.unregister("sample"); pluginRoleSettingsRegistry.unregister("secondary"); resetPluginEnabledStateForTests(); },
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
    assert.equal(f.stored.get("mira")?.plugin_state?.sample.enabled, true);
    assert.equal(f.state().dataset.dirty, "false");
  } finally { await f.close(); }
});

test("a committed secondary setting takes effect despite a later RPC failure and is not replayed on retry", async () => {
  const f = await fixture(true);
  try {
    await act(async () => f.save());
    assert.equal(f.stored.get("mira")?.plugin_state?.secondary.enabled, true);
    assert.equal(f.stored.get("mira")?.plugin_state?.sample.enabled, false);
    assert.equal(f.resourceActive(), true);
    f.deactivateResource();
    f.succeed();
    await act(async () => f.save());
    assert.equal(f.stored.get("mira")?.plugin_state?.sample.enabled, true);
    assert.equal(f.resourceActive(), false, "retry must preserve a resource deactivated after its committed save");
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
    assert.equal(f.stored.get("mira")?.plugin_state?.sample.enabled, true);
    assert.equal(f.state().dataset.saving, "false");
    assert.equal(f.state().dataset.dirty, "false");
    assert.match(f.messages.at(-1)!, /角色及插件设置已保存/);
    assert.doesNotMatch(f.messages.at(-1)!, /未保存/);
    await act(async () => f.state().querySelector("button")!.click());
    assert.equal(f.state().dataset.enabled, "true");
  } finally { await f.close(); }
});

test("a nullable role-list failure reports refresh failure while keeping the RPC commit", async () => {
  const f = await fixture();
  try {
    f.succeed(); f.rejectRefresh();
    await act(async () => f.save());
    assert.equal(f.stored.get("mira")?.plugin_state?.sample.enabled, true);
    assert.equal(f.state().dataset.enabled, "true");
    assert.equal(f.state().dataset.dirty, "false");
    assert.match(f.messages.at(-1)!, /已保存，后续处理失败.*刷新失败/);
    assert.equal(f.state().dataset.saving, "false");
    await act(async () => f.save());
    assert.equal(f.stored.get("mira")?.plugin_state?.sample.enabled, true);
  } finally { await f.close(); }
});

test("a communication close failure cannot turn a successful RPC commit into a write failure", async () => {
  const f = await fixture();
  try {
    f.succeed(); f.failClose();
    await act(async () => f.save());
    assert.equal(f.stored.get("mira")?.plugin_state?.sample.enabled, true);
    assert.equal(f.state().dataset.dirty, "false");
    assert.match(f.messages.at(-1)!, /已保存，后续处理失败.*close failed/);
    assert.doesNotMatch(f.messages.at(-1)!, /未保存/);
  } finally { await f.close(); }
});

test("a failed RPC keeps its write error when closing communication also fails", async () => {
  const f = await fixture();
  try {
    f.failClose();
    await act(async () => f.save());
    assert.equal(f.stored.get("mira")?.plugin_state?.sample.enabled, false);
    assert.equal(f.state().dataset.dirty, "true");
    assert.match(f.messages.at(-1)!, /插件设置未保存.*示例设置保存失败.*close failed/);
  } finally { await f.close(); }
});

test("a saved projection refreshes untouched draft fields before the next save", async () => {
  const f = await fixture();
  try {
    f.succeed();
    f.changeServerSettings({ limit: 50 });
    await act(async () => f.save());
    assert.equal(f.state().dataset.maxSteps, "50");
    assert.equal(f.state().dataset.dirty, "false");
    await act(async () => f.editSample({ mode: "quiet" }));
    await act(async () => f.save());
    assert.equal(f.stored.get("mira")?.plugin_state?.sample.limit, 50);
    assert.equal(f.stored.get("mira")?.plugin_state?.sample.mode, "quiet");
  } finally { await f.close(); }
});

test("saved projections merge untouched fields without erasing edits made during the RPC", async () => {
  const f = await fixture();
  try {
    f.succeed(); f.pause();
    let saving: Promise<void>;
    await act(async () => { saving = f.save(); await Promise.resolve(); });
    await act(async () => f.editSample({ batchSize: 9 }));
    f.changeServerSettings({ limit: 50 });
    await act(async () => { f.release(); await saving!; });
    assert.equal(f.state().dataset.maxSteps, "50");
    assert.equal(f.state().dataset.contentLimit, "9");
    assert.equal(f.state().dataset.dirty, "true");
    await act(async () => f.save());
    assert.equal(f.stored.get("mira")?.plugin_state?.sample.limit, 50);
    assert.equal(f.stored.get("mira")?.plugin_state?.sample.batchSize, 9);
    assert.equal(f.state().dataset.dirty, "false");
  } finally { await f.close(); }
});
