import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createEmptyRoleForm } from "../app/appState";
import { mountTestComponent, chooseSelectOption } from "@shiori/sdk/testing";
import type { RoleFormState } from "../shared/types";

let RoleVoiceSettingsPanel: typeof import("./RoleVoiceSettingsPanel").RoleVoiceSettingsPanel;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ RoleVoiceSettingsPanel } = await import("./RoleVoiceSettingsPanel"));
  await environment.cleanup();
});

describe("RoleVoiceSettingsPanel", () => {
  it("foregrounds the current voice while keeping technical parameters collapsed", () => {
    const markup = renderToStaticMarkup(<RoleVoiceSettingsPanel roleForm={{ ...createEmptyRoleForm(), voiceName: "晨雾", voiceProvider: "minimax", moodCatalog: ["平静"] }} onUpdate={() => undefined} />);

    assert.match(markup, /当前音色/);
    assert.match(markup, /晨雾/);
    assert.match(markup, /minimax 外部音色/);
    assert.match(markup, /编辑参数/);
    assert.match(markup, /情绪映射/);
    assert.doesNotMatch(markup, /拥有录音的使用授权/);
    assert.doesNotMatch(markup, /MiniMax voice_id/);
  });

  it("clears only the selected mood mapping when automatic detection is chosen", async () => {
    let form: RoleFormState = { ...createEmptyRoleForm(), moodCatalog: ["平静"], voiceMoodEmotions: { 平静: "happy", 开心: "happy" } };
    const view = await mountTestComponent(<RoleVoiceSettingsPanel roleForm={form} onUpdate={(next) => { form = typeof next === "function" ? next(form) : next; }} />);
    try {
      await chooseSelectOption("平静", "自动判断");
      assert.deepEqual(form.voiceMoodEmotions, { 开心: "happy" });
    } finally { await view.cleanup(); }
  });
});
