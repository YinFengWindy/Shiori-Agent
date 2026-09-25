import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { createEmptyRoleForm } from "../app/appState";
import type { ChannelSummary } from "../plugins/pluginBridgeClient";
import type { RoleChannelBinding } from "../shared/types";
import { RoleProactiveSettingsPanel } from "./RoleProactiveSettingsPanel";

describe("RoleProactiveSettingsPanel", () => {
  it("keeps execution parameters collapsed while exposing the selected delivery order", () => {
    const bindings: RoleChannelBinding[] = [{ channel: "telegram", chat_id: "100", chat_type: "private", allow_from: [] }, { channel: "qq", chat_id: "200", chat_type: "private", allow_from: [] }];
    const markup = renderToStaticMarkup(<RoleProactiveSettingsPanel bindings={bindings} channels={null} roleForm={{ ...createEmptyRoleForm(), proactiveEnabled: true, proactiveTargetChannel: "qq", proactiveTargetChatId: "200" }} onUpdate={() => undefined} />);

    assert.match(markup, /主动推送/);
    assert.match(markup, /首选投递位置/);
    assert.match(markup, /执行参数/);
    assert.match(markup, /qq · 200/);
    assert.doesNotMatch(markup, /Agent 模型/);
  });

  it("labels delivery targets with the channel catalog's display names", () => {
    const bindings: RoleChannelBinding[] = [{ channel: "qqbot", chat_id: "c2c:ABC", chat_type: "private", allow_from: [] }];
    const channels = [{ name: "qqbot", label: "QQBot", contactLabel: null, chatIdLabel: null, chatIdHint: null, chatTypes: [], pluginId: "qqbot", pluginEnabled: true, state: "active" as const, error: "", status: null }];
    const markup = renderToStaticMarkup(<RoleProactiveSettingsPanel bindings={bindings} channels={channels} roleForm={{ ...createEmptyRoleForm(), proactiveEnabled: true, proactiveTargetChannel: "qqbot", proactiveTargetChatId: "c2c:ABC" }} onUpdate={() => undefined} />);

    assert.match(markup, /QQBot · c2c:ABC/);
  });

  it("labels a binding by its declared session type and number without the internal prefix", () => {
    const bindings: RoleChannelBinding[] = [{ channel: "qq", chat_id: "gqq:831907794", chat_type: "group", allow_from: ["3"] }];
    const channels: ChannelSummary[] = [{
      name: "qq", label: "QQ（NapCat）", contactLabel: "QQ 号", chatIdLabel: null, chatIdHint: null,
      chatTypes: [
        { type: "private", label: "私聊", chatIdLabel: "QQ 号", chatIdHint: null, prefix: null },
        { type: "group", label: "群聊", chatIdLabel: "群号", chatIdHint: null, prefix: "gqq:" },
      ],
      pluginId: "qq", pluginEnabled: true, state: "active", error: "", status: null,
    }];
    const markup = renderToStaticMarkup(<RoleProactiveSettingsPanel bindings={bindings} channels={channels} roleForm={{ ...createEmptyRoleForm(), proactiveEnabled: true, proactiveTargetChannel: "qq", proactiveTargetChatId: "gqq:831907794" }} onUpdate={() => undefined} />);

    assert.match(markup, /QQ（NapCat） · 群聊 831907794/);
    // Only the picker's hidden form value keeps the stored chat id.
    assert.doesNotMatch(markup, />[^<]*gqq:/);
  });
});
