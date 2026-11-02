import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { createEmptyRoleForm } from "../app/appState";
import { resetPluginEnabledStateForTests, setPluginEnabledSnapshot } from "../plugins/pluginEnabledStateStore";
import { createSettingsDraft } from "../settings/testFixtures";
import { RoleCapabilitiesPanel } from "./RoleCapabilitiesPanel";

describe("RoleCapabilitiesPanel", () => {
  it("keeps natural chat available without any plugins and edits only its role draft", async () => {
    setPluginEnabledSnapshot([]);
    const initialForm = createEmptyRoleForm();
    let form = initialForm;
    const panel = () => <RoleCapabilitiesPanel activeRole={null} bridgeReady roleForm={form} onUpdate={(next) => { form = typeof next === "function" ? next(form) : next; }} />;
    const view = await mountTestComponent(panel(), { windowGlobals: { miraDesktop: { onEvent: () => () => undefined, invoke: async () => ({ error: null, payload: { providers: [] } }), readSettings: async () => ({ formData: createSettingsDraft() }) } } });
    try {
      const toggle = view.container.querySelector<HTMLButtonElement>('[role="switch"][aria-label="自然聊天"]');
      assert.ok(toggle);
      assert.equal(toggle.getAttribute("aria-checked"), "false");
      assert.equal(view.container.querySelectorAll('[aria-label="自然聊天"]').length, 1);
      await act(async () => toggle.click());
      await view.render(panel());
      assert.deepEqual(form, { ...initialForm, naturalChatEnabled: true });
      assert.equal(toggle.getAttribute("aria-checked"), "true");
      await act(async () => toggle.click());
      assert.deepEqual(form, initialForm);
    } finally {
      await view.cleanup();
      resetPluginEnabledStateForTests();
    }
  });

  it("renders capability names and current state labels", () => {
    const markup = renderToStaticMarkup(<RoleCapabilitiesPanel activeRole={null} bridgeReady roleForm={{ ...createEmptyRoleForm(), nsfwMemoryEnabled: true }} onUpdate={() => undefined} />);

    assert.match(markup, /运行能力/);
    assert.match(markup, /已启用/);
    assert.doesNotMatch(markup, /桌宠|主动推送/);
  });

});
