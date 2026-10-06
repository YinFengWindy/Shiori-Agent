import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { act } from "react";
import { createEmptyRoleForm } from "../app/appState";
import { mountTestComponent, chooseSelectOption } from "@yinfengwindy/shiori-sdk/testing";
import type { VoiceProviderDescriptor } from "../../../src/bridge/shared";
import type { RoleFormState } from "../shared/types";

let RoleVoiceSettingsPanel: typeof import("./RoleVoiceSettingsPanel").RoleVoiceSettingsPanel;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ RoleVoiceSettingsPanel } = await import("./RoleVoiceSettingsPanel"));
  await environment.cleanup();
});

const providers: VoiceProviderDescriptor[] = [{ id: "minimax", label: "MiniMax", kind: "tts", plugin_id: "minimax_tts", available: true, capabilities: { emotions: ["happy", "calm"], voice_cloning: true } }];

describe("RoleVoiceSettingsPanel", () => {
  it("foregrounds the current voice while keeping technical parameters collapsed", () => {
    const markup = renderToStaticMarkup(<RoleVoiceSettingsPanel providers={providers} roleForm={{ ...createEmptyRoleForm(), voiceName: "晨雾", voiceProvider: "minimax", moodCatalog: ["平静"] }} onUpdate={() => undefined} />);

    assert.match(markup, /当前音色/);
    assert.match(markup, /晨雾/);
    assert.match(markup, /MiniMax 外部音色/);
    assert.match(markup, /编辑参数/);
    assert.match(markup, /情绪映射/);
    assert.doesNotMatch(markup, /拥有录音的使用授权/);
    assert.doesNotMatch(markup, /MiniMax voice_id/);
  });

  it("clears only the selected mood mapping when automatic detection is chosen", async () => {
    let form: RoleFormState = { ...createEmptyRoleForm(), moodCatalog: ["平静"], voiceMoodEmotions: { 平静: "happy", 开心: "happy" } };
    const view = await mountTestComponent(<RoleVoiceSettingsPanel providers={providers} roleForm={form} onUpdate={(next) => { form = typeof next === "function" ? next(form) : next; }} />);
    try {
      await chooseSelectOption("平静", "自动判断");
      assert.deepEqual(form.voiceMoodEmotions, { 开心: "happy" });
    } finally { await view.cleanup(); }
  });

  it("switches provider-scoped voices and uses only the selected provider's emotions", async () => {
    let form: RoleFormState = { ...createEmptyRoleForm(), voiceId: "cloud-clone", voiceMoodEmotions: { 平静: "happy" } };
    const discovered: VoiceProviderDescriptor[] = [...providers, { id: "local", label: "Local", kind: "tts", plugin_id: "local", available: true, capabilities: { emotions: ["bright"], voice_cloning: false } }];
    const render = () => <RoleVoiceSettingsPanel providers={discovered} roleForm={form} onUpdate={(next) => { form = typeof next === "function" ? next(form) : next; }} />;
    const view = await mountTestComponent(render());
    try {
      const edit = Array.from(view.container.querySelectorAll("button")).find((button) => button.textContent?.includes("编辑参数"));
      assert.ok(edit);
      await act(async () => edit.click());
      await chooseSelectOption("角色语音服务商", "Local");
      await view.render(render());
      assert.equal(form.voiceId, "");
      assert.deepEqual(form.voiceMoodEmotions, {});
      await chooseSelectOption("平静", "bright");
      await view.render(render());
      assert.deepEqual(form.voiceMoodEmotions, { 平静: "bright" });
      await chooseSelectOption("角色语音服务商", "MiniMax");
      await view.render(render());
      assert.equal(form.voiceId, "cloud-clone");
      assert.deepEqual(form.voiceMoodEmotions, { 平静: "happy" });
    } finally { await view.cleanup(); }
  });

  it("keeps saved bindings visible when the selected plugin is unavailable", () => {
    const form = { ...createEmptyRoleForm(), voiceId: "cloud-clone", voiceName: "晨雾", voiceMoodEmotions: { 平静: "happy" } };
    const markup = renderToStaticMarkup(<RoleVoiceSettingsPanel providers={[]} globalVoiceEnabled roleForm={form} onUpdate={() => undefined} />);
    assert.match(markup, /服务商不可用/);
    assert.match(markup, /晨雾/);
    assert.match(markup, /happy（不受支持）/);
  });
});
