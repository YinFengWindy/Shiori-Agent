import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createEmptyRoleForm } from "../app/appState";
import type { ChannelState, ChannelSummary } from "../plugins/pluginBridgeClient";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { RoleChannelBinding, RoleFormState } from "../shared/types";
import { RoleChannelBindingsPanel } from "./RoleChannelBindingsPanel";

function channel(name: string, state: ChannelState, overrides: Partial<ChannelSummary> = {}): ChannelSummary {
  return {
    name, label: name, contactLabel: null, chatIdLabel: null, chatIdHint: null,
    pluginId: name, pluginEnabled: state !== "plugin_disabled", state, error: "", status: null,
    ...overrides,
  };
}

const desktop = channel("desktop", "active", { label: "桌面端", pluginId: null });
const qqbotDeclaration = { label: "QQBot", contactLabel: "QQBot 用户 OpenID", chatIdLabel: "私聊 chat_id", chatIdHint: "c2c:<用户 OpenID>" };
const qqbotBinding: RoleChannelBinding = { channel: "qqbot", chat_id: "c2c:ABC", allow_from: ["ABC"] };

function renderPanel(bindings: RoleChannelBinding[], channels: ChannelSummary[] | null) {
  return renderToStaticMarkup(<RoleChannelBindingsPanel activeRoleId="mira" bindings={bindings} channels={channels} onUpdate={() => undefined} />);
}

describe("RoleChannelBindingsPanel", () => {
  it("labels an active channel's fields from its declaration without a state marker", () => {
    const markup = renderPanel([qqbotBinding], [desktop, channel("qqbot", "active", qqbotDeclaration)]);

    assert.match(markup, /已配置 1 个投递位置/);
    assert.match(markup, /私聊 chat_id/);
    assert.match(markup, /placeholder="c2c:&lt;用户 OpenID&gt;"/);
    assert.match(markup, /联系人 ID（QQBot 用户 OpenID）/);
    assert.match(markup, /data-availability="editable"/);
    assert.doesNotMatch(markup, /未配置|已停用|异常/);
  });

  it("marks an enabled but unconfigured channel and points to where it is configured", () => {
    const markup = renderPanel([qqbotBinding], [desktop, channel("qqbot", "not_configured", qqbotDeclaration)]);

    assert.match(markup, />未配置</);
    assert.match(markup, /在 设置 › 插件 中完成配置后生效/);
    assert.match(markup, /role="combobox"/);
  });

  it("shows the plain label on the closed picker next to the state badge", async () => {
    const view = await mountTestComponent(<RoleChannelBindingsPanel activeRoleId="mira" bindings={[qqbotBinding]} channels={[desktop, channel("qqbot", "not_configured", qqbotDeclaration)]} onUpdate={() => undefined} />);
    try {
      const trigger = view.container.querySelector<HTMLButtonElement>('[role="combobox"][aria-label="渠道"]');
      assert.ok(trigger);
      assert.equal(trigger.textContent, "QQBot");
    } finally {
      await view.cleanup();
    }
  });

  it("shows a failed channel's error on its binding", () => {
    const markup = renderPanel([qqbotBinding], [desktop, channel("qqbot", "failed", { ...qqbotDeclaration, error: "网关鉴权失败" })]);

    assert.match(markup, />异常</);
    assert.match(markup, /网关鉴权失败/);
    assert.match(markup, /data-availability="editable"/);
  });

  it("keeps a binding of a disabled plugin visible and read-only with a notice", () => {
    const markup = renderPanel([qqbotBinding], [desktop, channel("qqbot", "plugin_disabled", qqbotDeclaration)]);

    assert.match(markup, /data-availability="plugin_disabled"/);
    assert.match(markup, />已停用</);
    assert.match(markup, /提供该渠道的插件已停用/);
    assert.match(markup, /<input[^>]*readOnly="" value="c2c:ABC"/);
    assert.match(markup, /<input[^>]*readOnly="" value="ABC"/);
    assert.doesNotMatch(markup, /role="combobox"/);
    assert.match(markup, /aria-label="移除QQBot绑定"/);
  });

  it("disables adding until the channel list has loaded", () => {
    assert.match(renderPanel([], null), /<button[^>]*disabled=""[^>]*aria-label="添加渠道绑定"/);
    assert.doesNotMatch(renderPanel([], [desktop]), /<button[^>]*disabled=""[^>]*aria-label="添加渠道绑定"/);
  });

  it("removes a disabled plugin's binding and adds new bindings on an enabled channel in the saved format", async () => {
    let latest: RoleFormState | undefined;
    const channels = [desktop, channel("qqbot", "plugin_disabled", qqbotDeclaration), channel("telegram", "active", { label: "Telegram", pluginId: null })];
    function Harness() {
      const [form, setForm] = useState<RoleFormState>({ ...createEmptyRoleForm(), channelBindings: [qqbotBinding], proactiveTargetChannel: "qqbot", proactiveTargetChatId: "c2c:ABC" });
      latest = form;
      return <RoleChannelBindingsPanel activeRoleId="mira" bindings={form.channelBindings ?? []} channels={channels} onUpdate={setForm} />;
    }
    const view = await mountTestComponent(<Harness />);
    try {
      const button = (label: string) => {
        const element = view.container.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`);
        assert.ok(element, `Missing button: ${label}`);
        return element;
      };
      await act(async () => button("添加渠道绑定").click());
      assert.deepEqual(latest?.channelBindings, [qqbotBinding, { channel: "telegram", chat_id: "", allow_from: [] }]);

      await act(async () => button("移除QQBot绑定").click());
      assert.deepEqual(latest?.channelBindings, [{ channel: "telegram", chat_id: "", allow_from: [] }]);
      // Removing the proactive target's binding clears the dangling target.
      assert.equal(latest?.proactiveTargetChannel, "");
    } finally {
      await view.cleanup();
    }
  });
});
