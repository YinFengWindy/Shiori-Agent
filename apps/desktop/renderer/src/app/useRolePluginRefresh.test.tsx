import assert from "node:assert/strict";
import { test } from "node:test";
import { act, useState } from "react";
import { createEmptyRoleForm } from "./appState";
import { useRolePluginRefresh } from "./useRolePluginRefresh";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { pluginRoleSettingsRegistry } from "../plugins/pluginFeatureRegistry";
import { buildPluginRoleDraftUpdates } from "../plugins/pluginRoleSettings";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";

const role: RoleRecord = {
  id: "mira", name: "Mira", description: "", system_prompt: "test", runtime_config: {},
  avatar: null, avatar_abs: null, chat_background: null, chat_background_abs: null,
  illustrations: [], illustrations_abs: [], asset_categories: [], asset_category_bindings: {},
  created_at: "", updated_at: "",
};

test("plugin asset refresh clears stale enabled drafts while retaining unsaved role edits", async () => {
  pluginRoleSettingsRegistry.register({ pluginId: "sample", storage: "plugin", Component: () => null,
    read: (state) => ({ enabled: state.enabled === true }),
  });
  setPluginEnabledSnapshot([{ id: "sample", enabled: true, state: "ACTIVE" }]);
  let persisted = { ...role, plugin_state: { sample: { enabled: true, available: true } } };
  let draft: RoleFormState = { ...createEmptyRoleForm(), name: "Unsaved name", pluginSettings: { sample: { enabled: true } } };
  let refresh = async () => {};
  function Harness() {
    const [form, setForm] = useState<RoleFormState>(draft);
    draft = { ...form, pluginSettings: { sample: { enabled: form.pluginSettings.sample?.enabled === true } } };
    refresh = useRolePluginRefresh({ detailRoleId: role.id, detailRole: persisted, roleFormRef: { current: form },
      loadRolesFromBridge: async () => [persisted], updateRoleForm: setForm,
      setError: (error) => { throw new Error(error); },
    });
    return <span>{form.name}</span>;
  }
  const view = await mountTestComponent(<Harness />);
  try {
    persisted = { ...role, plugin_state: { sample: { enabled: false, available: false } } };
    await act(async () => { await refresh(); });
    assert.deepEqual(draft.pluginSettings.sample, { enabled: false });
    assert.equal(draft.name, "Unsaved name");
    assert.deepEqual(buildPluginRoleDraftUpdates(draft.pluginSettings, persisted.plugin_state), {});
  } finally {
    await view.cleanup(); pluginRoleSettingsRegistry.unregister("sample"); resetPluginEnabledStateForTests();
  }
});

test("enabling a plugin reloads its projection for a role cached while disabled", async () => {
  pluginRoleSettingsRegistry.register({ pluginId: "sample", storage: "plugin", Component: () => null,
    read: (state) => ({ enabled: state.enabled === true }),
  });
  setPluginEnabledSnapshot([{ id: "sample", enabled: false, state: "DISABLED" }]);
  let persisted = role;
  let draft = createEmptyRoleForm();
  let calls = 0;
  let edit = () => {};
  function Harness() {
    const [form, setForm] = useState(createEmptyRoleForm);
    draft = form;
    edit = () => setForm((current) => ({ ...current, pluginSettings: { sample: { enabled: false } } }));
    useRolePluginRefresh({ detailRoleId: role.id, detailRole: persisted, roleFormRef: { current: form },
      loadRolesFromBridge: async () => { calls += 1; return [persisted]; }, updateRoleForm: setForm,
      setError: (error) => { throw new Error(error); },
    });
    return null;
  }
  const view = await mountTestComponent(<Harness />);
  try {
    assert.equal(draft.pluginSettings.sample, undefined);
    persisted = { ...role, plugin_state: { sample: { enabled: true, available: true } } };
    await act(async () => { setPluginEnabledSnapshot([{ id: "sample", enabled: true, state: "ACTIVE" }]); });
    assert.equal(calls, 2);
    assert.deepEqual(draft.pluginSettings.sample, { enabled: true });
    await act(async () => { edit(); });
    await act(async () => { setPluginEnabledSnapshot([{ id: "sample", enabled: true, state: "ACTIVE" }]); });
    assert.deepEqual(draft.pluginSettings.sample, { enabled: false });
    assert.equal(calls, 2, "an identical roster must not refetch or reset drafts");
  } finally {
    await view.cleanup(); pluginRoleSettingsRegistry.unregister("sample"); resetPluginEnabledStateForTests();
  }
});


test("an in-flight refresh does not overwrite an edit made after the request began", async () => {
  pluginRoleSettingsRegistry.register({ pluginId: "sample", storage: "plugin", Component: () => null,
    read: (state) => ({ enabled: state.enabled === true }),
  });
  setPluginEnabledSnapshot([{ id: "sample", enabled: true, state: "ACTIVE" }]);
  const persisted = { ...role, plugin_state: { sample: { enabled: false, available: true } } };
  let resolve: (roles: RoleRecord[]) => void = () => {};
  const pending = new Promise<RoleRecord[]>((done) => { resolve = done; });
  let edit = () => {};
  let draft = createEmptyRoleForm();
  function Harness() {
    const [form, setForm] = useState<RoleFormState>(() => ({ ...createEmptyRoleForm(), pluginSettings: { sample: { enabled: false } } }));
    draft = form;
    edit = () => setForm((current) => ({ ...current, pluginSettings: { sample: { enabled: true } } }));
    useRolePluginRefresh({ detailRoleId: role.id, detailRole: persisted, roleFormRef: { current: form },
      loadRolesFromBridge: () => pending, updateRoleForm: setForm,
      setError: (error) => { throw new Error(error); },
    });
    return null;
  }
  const view = await mountTestComponent(<Harness />);
  try {
    await act(async () => { edit(); });
    await act(async () => { resolve([persisted]); });
    assert.deepEqual(draft.pluginSettings.sample, { enabled: true });
  } finally {
    await view.cleanup(); pluginRoleSettingsRegistry.unregister("sample"); resetPluginEnabledStateForTests();
  }
});
