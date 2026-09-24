import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createEmptyRoleForm } from "../app/appState";
import { RoleProactiveSettingsPanel } from "./RoleProactiveSettingsPanel";

describe("RoleProactiveSettingsPanel", () => {
  it("keeps execution parameters collapsed while exposing the selected delivery order", () => {
    const bindings = [{ channel: "telegram", chat_id: "100", allow_from: [] }, { channel: "qq", chat_id: "200", allow_from: [] }];
    const markup = renderToStaticMarkup(<RoleProactiveSettingsPanel bindings={bindings} channels={null} roleForm={{ ...createEmptyRoleForm(), proactiveEnabled: true, proactiveTargetChannel: "qq", proactiveTargetChatId: "200" }} onUpdate={() => undefined} />);

    assert.match(markup, /主动推送/);
    assert.match(markup, /首选投递位置/);
    assert.match(markup, /执行参数/);
    assert.match(markup, /qq · 200/);
    assert.doesNotMatch(markup, /Agent 模型/);
  });

  it("labels delivery targets with the channel catalog's display names", () => {
    const bindings = [{ channel: "qqbot", chat_id: "c2c:ABC", allow_from: [] }];
    const channels = [{ name: "qqbot", label: "QQBot", contactLabel: null, chatIdLabel: null, chatIdHint: null, pluginId: "qqbot", pluginEnabled: true, state: "active" as const, error: "", status: null }];
    const markup = renderToStaticMarkup(<RoleProactiveSettingsPanel bindings={bindings} channels={channels} roleForm={{ ...createEmptyRoleForm(), proactiveEnabled: true, proactiveTargetChannel: "qqbot", proactiveTargetChatId: "c2c:ABC" }} onUpdate={() => undefined} />);

    assert.match(markup, /QQBot · c2c:ABC/);
  });
});
