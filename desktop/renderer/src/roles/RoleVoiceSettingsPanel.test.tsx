import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createEmptyRoleForm } from "../app/appState";
import { RoleVoiceSettingsPanel } from "./RoleVoiceSettingsPanel";

describe("RoleVoiceSettingsPanel", () => {
  it("foregrounds the current voice while keeping technical parameters collapsed", () => {
    const markup = renderToStaticMarkup(<RoleVoiceSettingsPanel bridgeReady roleForm={{ ...createEmptyRoleForm(), voiceName: "晨雾", voiceProvider: "minimax", moodCatalog: ["平静"] }} onUpdate={() => undefined} />);

    assert.match(markup, /当前音色/);
    assert.match(markup, /晨雾/);
    assert.match(markup, /minimax 外部音色/);
    assert.match(markup, /编辑音色参数/);
    assert.match(markup, /情绪映射/);
    assert.doesNotMatch(markup, /MiniMax voice_id/);
  });
});
