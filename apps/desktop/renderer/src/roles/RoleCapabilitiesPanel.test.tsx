import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { mountTestComponent } from "@shiori/plugin-sdk/testing";
import { createEmptyRoleForm } from "../app/appState";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";
import { createSettingsDraft } from "../settings/testFixtures";
import type { RoleFormState } from "../shared/types";
import { RoleCapabilitiesPanel } from "./RoleCapabilitiesPanel";

describe("RoleCapabilitiesPanel", () => {
  it("renders capability names and current state labels", () => {
    const markup = renderToStaticMarkup(<RoleCapabilitiesPanel activeRole={null} bridgeReady roleForm={{ ...createEmptyRoleForm(), nsfwMemoryEnabled: true }} onUpdate={() => undefined} />);

    assert.match(markup, /运行能力/);
    assert.match(markup, /已启用/);
    assert.doesNotMatch(markup, /桌宠/);
  });

  it("groups the proactive switch with runtime capabilities and places its parameters below voice", async () => {
    setPluginEnabledSnapshot([]);
    const initialForm = { ...createEmptyRoleForm(), proactiveProfile: "quiet", proactiveAgentMaxSteps: 42, proactiveDriftEnabled: true };
    let form: RoleFormState = initialForm;
    const panel = () => <RoleCapabilitiesPanel activeRole={null} bridgeReady roleForm={form} onUpdate={(next) => { form = typeof next === "function" ? next(form) : next; }} />;
    const view = await mountTestComponent(panel(), { windowGlobals: { miraDesktop: { readSettings: async () => ({ formData: createSettingsDraft() }) } } });
    try {
      assert.deepEqual(Array.from(view.container.querySelectorAll("h2"), (heading) => heading.textContent), ["运行能力", "声音", "主动推送"]);
      const capability = view.container.querySelector('[data-testid="role-proactive-capability"]');
      assert.equal(capability?.closest("section")?.querySelector("h2")?.textContent, "运行能力");
      assert.match(capability?.textContent ?? "", /未启用/);
      const toggle = capability?.querySelector<HTMLButtonElement>('[role="switch"][aria-label="主动推送"]');
      assert.ok(toggle);
      assert.equal(view.container.querySelectorAll('[role="switch"][aria-label="主动推送"]').length, 1);

      await act(async () => toggle.click());
      assert.deepEqual(form, { ...initialForm, proactiveEnabled: true });
      await view.render(panel());
      assert.equal(toggle.getAttribute("aria-checked"), "true");
      assert.match(capability?.textContent ?? "", /已启用/);

      await act(async () => toggle.click());
      assert.deepEqual(form, initialForm);
      await view.render(panel());
      assert.equal(toggle.getAttribute("aria-checked"), "false");
      assert.ok(view.container.querySelector('[aria-label="推送策略"]'), "disabling proactive push keeps its parameters available");
    } finally {
      await view.cleanup();
      resetPluginEnabledStateForTests();
    }
  });

  for (const devMode of [false, true]) {
    it(`preserves developer strategy visibility with devMode=${devMode}`, async () => {
      setPluginEnabledSnapshot([]);
      const settings = createSettingsDraft();
      settings.advanced.devMode = devMode;
      const view = await mountTestComponent(
        <RoleCapabilitiesPanel activeRole={null} bridgeReady roleForm={createEmptyRoleForm()} onUpdate={() => undefined} />,
        { windowGlobals: { miraDesktop: { readSettings: async () => ({ formData: settings }) } } },
      );
      try {
        const picker = view.container.querySelector<HTMLButtonElement>('[role="combobox"][aria-label="推送策略"]');
        assert.ok(picker);
        await act(async () => picker.click());
        const options = Array.from(document.querySelectorAll('[role="option"]'), (option) => option.textContent);
        assert.deepEqual(options, devMode ? ["日常", "低打扰", "开发验证"] : ["日常", "低打扰"]);
      } finally {
        await view.cleanup();
        resetPluginEnabledStateForTests();
      }
    });
  }
});
