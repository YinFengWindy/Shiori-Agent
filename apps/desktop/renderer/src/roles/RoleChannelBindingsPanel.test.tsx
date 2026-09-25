import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { act, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createEmptyRoleForm } from "../app/appState";
import type { ChannelState, ChannelSummary } from "../plugins/pluginBridgeClient";
import { changeInputValue, mountTestComponent } from "../shared/testing/domTestHarness";
import { chooseSelectOption } from "../shared/testing/selectTestActions";
import type { RoleChannelBinding, RoleFormState } from "../shared/types";

// Base UI's Select only opens its list when first loaded inside a DOM window.
let RoleChannelBindingsPanel: typeof import("./RoleChannelBindingsPanel").RoleChannelBindingsPanel;
before(async () => {
  const environment = await mountTestComponent(null);
  ({ RoleChannelBindingsPanel } = await import("./RoleChannelBindingsPanel"));
  await environment.cleanup();
});

function channel(name: string, state: ChannelState, overrides: Partial<ChannelSummary> = {}): ChannelSummary {
  return {
    name, label: name, contactLabel: null, chatTypes: [],
    pluginId: name, pluginEnabled: state !== "plugin_disabled", state, error: "", status: null,
    ...overrides,
  };
}

const desktop = channel("desktop", "active", { label: "桌面端", pluginId: null });
const qqbotDeclaration: Partial<ChannelSummary> = {
  label: "QQBot", contactLabel: "QQBot 用户 OpenID",
  chatTypes: [{ type: "private", label: "私聊", chatIdLabel: "用户 OpenID", chatIdHint: "对方的用户 OpenID", prefix: "c2c:" }],
};
const qqbotBinding: RoleChannelBinding = { channel: "qqbot", chat_id: "c2c:ABC", chat_type: "private", allow_from: ["contact-1"] };
const telegramDeclaration: Partial<ChannelSummary> = {
  label: "Telegram",
  chatTypes: [
    { type: "private", label: "私聊", chatIdLabel: "用户 ID", chatIdHint: null, prefix: null },
    { type: "group", label: "群聊", chatIdLabel: "群组 ID", chatIdHint: null, prefix: null },
  ],
};

const qqDeclaration: Partial<ChannelSummary> = {
  label: "QQ（NapCat）", contactLabel: "QQ 号",
  chatTypes: [
    { type: "private", label: "私聊", chatIdLabel: "QQ 号", chatIdHint: "对方的 QQ 号", prefix: null },
    { type: "group", label: "群聊", chatIdLabel: "群号", chatIdHint: "QQ 群号", prefix: "gqq:" },
  ],
};
const typedChannels = [desktop, channel("qq", "active", qqDeclaration), channel("qqbot", "active", qqbotDeclaration), channel("telegram", "active", telegramDeclaration)];

/** Mounts the panel over live form state so edits round-trip through the saved binding shape. */
async function mountEditablePanel(initial: RoleChannelBinding[]) {
  const state: { form: RoleFormState | undefined } = { form: undefined };
  function Harness() {
    const [form, setForm] = useState<RoleFormState>({ ...createEmptyRoleForm(), channelBindings: initial });
    state.form = form;
    return <RoleChannelBindingsPanel activeRoleId="mira" bindings={form.channelBindings ?? []} channels={typedChannels} onUpdate={setForm} onOpenPluginSettings={() => undefined} />;
  }
  const view = await mountTestComponent(<Harness />);
  const numberInput = (label: string) => {
    const field = Array.from(view.container.querySelectorAll("label")).find((item) => item.querySelector("span")?.textContent === label);
    const input = field?.querySelector("input");
    assert.ok(input, `Missing number field: ${label}`);
    return input;
  };
  return { view, state, numberInput };
}

function renderPanel(bindings: RoleChannelBinding[], channels: ChannelSummary[] | null) {
  return renderToStaticMarkup(<RoleChannelBindingsPanel activeRoleId="mira" bindings={bindings} channels={channels} onUpdate={() => undefined} onOpenPluginSettings={() => undefined} />);
}

describe("RoleChannelBindingsPanel", () => {
  it("labels an active channel's fields from its declaration without a state marker", () => {
    const markup = renderPanel([qqbotBinding], [desktop, channel("qqbot", "active", qqbotDeclaration)]);

    assert.match(markup, />用户 OpenID</);
    assert.match(markup, /placeholder="对方的用户 OpenID"/);
    assert.match(markup, /联系人 ID（QQBot 用户 OpenID）/);
    assert.match(markup, /data-availability="editable"/);
    assert.doesNotMatch(markup, /未配置|已停用|异常/);
  });

  it("marks an enabled but unconfigured channel and points to where it is configured", () => {
    const markup = renderPanel([qqbotBinding], [desktop, channel("qqbot", "not_configured", qqbotDeclaration)]);

    assert.match(markup, />未配置</);
    assert.match(markup, /在<button[^>]*data-testid="role-channel-open-plugin-settings"[^>]*>设置 › 插件<\/button>中完成配置后生效/);
    assert.match(markup, /role="combobox"/);
  });

  it("opens the providing plugin's settings from the unconfigured notice", async () => {
    const opened: Array<string | null> = [];
    const view = await mountTestComponent(<RoleChannelBindingsPanel activeRoleId="mira" bindings={[qqbotBinding]} channels={[desktop, channel("qqbot", "not_configured", qqbotDeclaration)]} onUpdate={() => undefined} onOpenPluginSettings={(pluginId) => opened.push(pluginId)} />);
    try {
      const link = view.container.querySelector<HTMLButtonElement>("[data-testid=\"role-channel-open-plugin-settings\"]");
      assert.ok(link);
      await act(async () => link.click());
      assert.deepEqual(opened, ["qqbot"]);
    } finally {
      await view.cleanup();
    }
  });

  it("shows the plain label on the closed picker next to the state badge", async () => {
    const view = await mountTestComponent(<RoleChannelBindingsPanel activeRoleId="mira" bindings={[qqbotBinding]} channels={[desktop, channel("qqbot", "not_configured", qqbotDeclaration)]} onUpdate={() => undefined} onOpenPluginSettings={() => undefined} />);
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
    assert.match(markup, /<input[^>]*placeholder="对方的用户 OpenID" readOnly="" value="ABC"/);
    assert.match(markup, /<input[^>]*readOnly="" value="contact-1"/);
    assert.doesNotMatch(markup, /role="combobox"/);
    assert.match(markup, /aria-label="移除QQBot绑定"/);
  });

  it("disables adding until the channel list has loaded", () => {
    assert.match(renderPanel([], null), /<button[^>]*disabled=""[^>]*aria-label="添加渠道绑定"/);
    assert.doesNotMatch(renderPanel([], [desktop]), /<button[^>]*disabled=""[^>]*aria-label="添加渠道绑定"/);
  });

  it("removes a disabled plugin's binding and adds new bindings on an enabled channel in the saved format", async () => {
    let latest: RoleFormState | undefined;
    const channels = [desktop, channel("qqbot", "plugin_disabled", qqbotDeclaration), channel("telegram", "active", telegramDeclaration)];
    function Harness() {
      const [form, setForm] = useState<RoleFormState>({ ...createEmptyRoleForm(), channelBindings: [qqbotBinding], proactiveTargetChannel: "qqbot", proactiveTargetChatId: "c2c:ABC" });
      latest = form;
      return <RoleChannelBindingsPanel activeRoleId="mira" bindings={form.channelBindings ?? []} channels={channels} onUpdate={setForm} onOpenPluginSettings={() => undefined} />;
    }
    const view = await mountTestComponent(<Harness />);
    try {
      const button = (label: string) => {
        const element = view.container.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`);
        assert.ok(element, `Missing button: ${label}`);
        return element;
      };
      await act(async () => button("添加渠道绑定").click());
      assert.deepEqual(latest?.channelBindings, [qqbotBinding, { channel: "telegram", chat_id: "", chat_type: "private", allow_from: [] }]);

      await act(async () => button("移除QQBot绑定").click());
      assert.deepEqual(latest?.channelBindings, [{ channel: "telegram", chat_id: "", chat_type: "private", allow_from: [] }]);
      // Removing the proactive target's binding clears the dangling target.
      assert.equal(latest?.proactiveTargetChannel, "");
    } finally {
      await view.cleanup();
    }
  });

  it("saves a group chosen by type as the prefixed chat id and reopens it as type plus number", async () => {
    const { view, state, numberInput } = await mountEditablePanel([]);
    try {
      const add = view.container.querySelector<HTMLButtonElement>('button[aria-label="添加渠道绑定"]');
      assert.ok(add);
      await act(async () => add.click());
      assert.deepEqual(state.form?.channelBindings, [{ channel: "qq", chat_id: "", chat_type: "private", allow_from: [] }]);

      await chooseSelectOption("类型", "群聊");
      await changeInputValue(numberInput("群号"), "831907794");
      assert.deepEqual(state.form?.channelBindings, [{ channel: "qq", chat_id: "gqq:831907794", chat_type: "group", allow_from: [] }]);
    } finally {
      await view.cleanup();
    }

    const reopened = await mountEditablePanel([{ channel: "qq", chat_id: "gqq:831907794", chat_type: "group", allow_from: ["3"] }]);
    try {
      const trigger = reopened.view.container.querySelector<HTMLButtonElement>('[role="combobox"][aria-label="类型"]');
      assert.equal(trigger?.textContent, "群聊");
      assert.equal(reopened.numberInput("群号").value, "831907794");
    } finally {
      await reopened.view.cleanup();
    }
  });

  it("saves a private chat's number as is and re-derives the prefix when the type changes", async () => {
    const { view, state, numberInput } = await mountEditablePanel([{ channel: "qq", chat_id: "", chat_type: "private", allow_from: [] }]);
    try {
      await changeInputValue(numberInput("QQ 号"), "3174898512");
      assert.deepEqual(state.form?.channelBindings, [{ channel: "qq", chat_id: "3174898512", chat_type: "private", allow_from: [] }]);

      await chooseSelectOption("类型", "群聊");
      assert.deepEqual(state.form?.channelBindings?.[0], { channel: "qq", chat_id: "gqq:3174898512", chat_type: "group", allow_from: [] });
      await chooseSelectOption("类型", "私聊");
      assert.deepEqual(state.form?.channelBindings?.[0], { channel: "qq", chat_id: "3174898512", chat_type: "private", allow_from: [] });
    } finally {
      await view.cleanup();
    }
  });

  it("shows a single declared type read-only and hides its prefix from the number", () => {
    const markup = renderPanel([qqbotBinding], [desktop, channel("qqbot", "active", qqbotDeclaration)]);

    assert.match(markup, /role="textbox" aria-label="类型" aria-readonly="true">私聊</);
    assert.match(markup, /用户 OpenID/);
    assert.match(markup, /<input[^>]*value="ABC"/);
    assert.doesNotMatch(markup, /value="c2c:ABC"/);
  });

  it("shows a binding whose plugin is gone read-only by its stored type and chat id", () => {
    const markup = renderPanel([{ channel: "gone", chat_id: "gqq:831907794", chat_type: "group", allow_from: ["1"] }], typedChannels);

    assert.match(markup, /data-availability="missing"/);
    assert.match(markup, /role="textbox" aria-label="类型" aria-readonly="true">群聊</);
    assert.match(markup, /<input[^>]*readOnly="" value="gqq:831907794"/);
    assert.doesNotMatch(markup, /role="combobox"/);
  });

  it("shows the desktop session without a type and read-only", () => {
    const markup = renderPanel([{ channel: "desktop", chat_id: "role:mira", chat_type: "private", allow_from: [] }], typedChannels);

    assert.doesNotMatch(markup, /aria-label="类型"/);
    assert.match(markup, /<input[^>]*readOnly="" value="role:mira"/);
  });
});
