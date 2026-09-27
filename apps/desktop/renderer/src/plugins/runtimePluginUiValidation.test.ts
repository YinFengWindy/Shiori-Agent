import assert from "node:assert/strict";
import { test } from "node:test";
import { memo, forwardRef } from "react";
import { retiredPluginUiContribution, validateRuntimePluginUi } from "./runtimePluginUiValidation";

test("identity and all contribution shapes are validated, including wrapped React components", () => {
  const component = () => null;
  for (const wrapped of [component, memo(component), forwardRef(component)]) {
    assert.doesNotThrow(() => validateRuntimePluginUi({ pluginId: "demo", navPage: { label: "Demo", component: wrapped } }, "demo"));
  }
  assert.throws(() => validateRuntimePluginUi({ pluginId: "other" }, "demo"), /identity/);
  for (const contribution of [
    { navPage: { label: "Demo", component: 1 } },
    { navPage: { component } },
    { navPage: { component, label: "Demo", sidebar: 1 } },
    { settingsSection: { label: "Settings", kind: "invalid" } },
    { chatImageActions: {} },
    { accountDetail: { component: 1 } },
    { roleSettings: { Component: component, read: () => ({}), pluginId: "other" } },
    { roleSettings: { Component: component, read: () => ({}), storage: "runtime" } },
  ]) assert.throws(() => validateRuntimePluginUi({ pluginId: "demo", ...contribution }, "demo"));
  assert.doesNotThrow(() => validateRuntimePluginUi({ pluginId: "demo", roleSettings: { Component: component, read: () => ({}), storage: "plugin" } }, "demo"));
  assert.doesNotThrow(() => validateRuntimePluginUi({ pluginId: "demo", accountDetail: { component } }, "demo"));
});

test("a package still declaring the retired roleMemory contribution is rejected with an explicit diagnostic", () => {
  const component = () => null;
  // Even a well-formed old contribution fails, alongside otherwise valid slots.
  assert.throws(
    () => validateRuntimePluginUi({ pluginId: "demo", navPage: { label: "Demo", component }, roleMemory: { component } }, "demo"),
    /roleMemory is retired.*roles\.memory\.documents/,
  );
  assert.match(retiredPluginUiContribution({ roleMemory: undefined }) ?? "", /roleMemory is retired/);
  assert.equal(retiredPluginUiContribution({ navPage: {} }), null);
});
