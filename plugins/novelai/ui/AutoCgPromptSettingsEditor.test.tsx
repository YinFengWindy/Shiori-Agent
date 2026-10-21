import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { PluginHostServicesProvider, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";
import { changeInputValue, createFakeHostServices, createFakePluginClient, mountTestComponent } from "@yinfengwindy/shiori-sdk/testing";
import { AutoCgPromptSettingsEditor } from "./AutoCgPromptSettingsEditor";
import { useAutoCgPromptSettings } from "./useAutoCgPromptSettings";

function Editor({ client }: { client: PluginRpcClient }) {
  const settings = useAutoCgPromptSettings(client, "mira");
  return <AutoCgPromptSettingsEditor roleId="mira" settings={settings} disabled={false} />;
}

test("the editor shows load errors, then preserves a failed draft until retry succeeds", async () => {
  const { host } = createFakeHostServices();
  let failRead = true;
  let failSave = true;
  let stored = "原有要求";
  const savedDrafts: unknown[] = [];
  const client = createFakePluginClient({ call: async <T,>(method: string, payload?: Record<string, unknown>) => {
    if (method === "role_settings.get") {
      if (failRead) throw new Error("读取失败");
    } else if (method === "role_settings.set") {
      savedDrafts.push(payload?.prompt_instructions);
      if (failSave) throw new Error("保存失败");
      stored = String(payload?.prompt_instructions);
    } else assert.fail(`unexpected method ${method}`);
    return { prompt_instructions: stored } as T;
  } });
  const view = await mountTestComponent(<PluginHostServicesProvider services={host}><Editor client={client} /></PluginHostServicesProvider>);
  const click = async (label: string) => act(async () => {
    const button = Array.from(view.container.querySelectorAll("button")).find((item) => item.textContent === label);
    assert.ok(button);
    button.click();
  });
  try {
    assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /读取失败/);
    assert.equal(view.container.querySelector("textarea"), null);
    failRead = false;
    await click("重新加载");
    const field = view.container.querySelector("textarea")!;
    assert.equal(field.value, stored);
    await changeInputValue(field, "保留猫耳\n柔和光线");
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 450)); });
    assert.match(view.container.querySelector('[role="alert"]')?.textContent ?? "", /保存失败/);
    assert.equal(view.container.querySelector('[role="status"]')?.getAttribute("data-save-phase"), "error");
    assert.equal(stored, "原有要求");
    assert.equal(field.value, "保留猫耳\n柔和光线");
    failSave = false;
    await click("重试");
    assert.equal(stored, "保留猫耳\n柔和光线");
    assert.deepEqual(savedDrafts, [stored, stored]);
    assert.equal(view.container.querySelector('[role="alert"]'), null);
  } finally { await view.cleanup(); }
});
