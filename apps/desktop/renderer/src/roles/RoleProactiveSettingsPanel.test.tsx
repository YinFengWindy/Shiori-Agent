import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { act, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createEmptyRoleForm } from "../app/appState";
import type { ChannelSummary } from "../plugins/pluginBridgeClient";
import { mountTestComponent } from "../shared/testing/domTestHarness";
import type { RoleChannelBinding, RoleFormState } from "../shared/types";
import { RoleProactiveSettingsPanel } from "./RoleProactiveSettingsPanel";

const qqChannel: ChannelSummary = {
  name: "qq", label: "QQ（NapCat）", contactLabel: "QQ 号",
  chatTypes: [
    { type: "private", label: "私聊", chatIdLabel: "QQ 号", chatIdHint: null, prefix: null },
    { type: "group", label: "群聊", chatIdLabel: "群号", chatIdHint: null, prefix: "gqq:" },
  ],
  pluginId: "qq", pluginEnabled: true, state: "active", error: "", status: null,
};
const desktop: RoleChannelBinding = { channel: "desktop", chat_id: "role:mira", chat_type: "private", blocked_senders: [] };
const qqPrivate: RoleChannelBinding = { channel: "qq", chat_id: "3174898512", chat_type: "private", blocked_senders: [] };
const qqGroup: RoleChannelBinding = { channel: "qq", chat_id: "gqq:831907794", chat_type: "group", blocked_senders: ["3"] };

function checkboxes(container: HTMLElement) {
  return Array.from(container.querySelectorAll<HTMLInputElement>('[data-testid="role-proactive-candidates"] input[type="checkbox"]'));
}

describe("RoleProactiveSettingsPanel", () => {
  it("lists bound sessions as checkable candidates and marks the backend's current one", () => {
    const markup = renderToStaticMarkup(
      <RoleProactiveSettingsPanel
        bindings={[desktop, qqPrivate, qqGroup, { ...qqPrivate, chat_id: "" }]}
        channels={[qqChannel]}
        currentTarget={{ channel: "qq", chat_id: "3174898512" }}
        roleForm={{ ...createEmptyRoleForm(), proactiveEnabled: true, proactiveCandidates: [{ channel: "desktop", chat_id: "role:mira" }, { channel: "qq", chat_id: "3174898512" }] }}
        onUpdate={() => undefined}
      />,
    );

    assert.match(markup, /接收会话/);
    // Labels by session type and number; the desktop session is just its channel.
    assert.match(markup, /桌面端<\/span>/);
    assert.match(markup, /QQ（NapCat） · 私聊 3174898512<\/span><span[^>]*data-testid="role-proactive-current"[^>]*>当前</);
    assert.match(markup, /QQ（NapCat） · 群聊 831907794/);
    assert.doesNotMatch(markup, />[^<]*gqq:/);
    assert.equal(markup.match(/type="checkbox"/g)?.length, 3);
    assert.equal(markup.match(/checked=""/g)?.length, 2);
    assert.equal(markup.match(/>当前</g)?.length, 1);
    assert.match(markup, /推送策略/);
    assert.match(markup, /执行参数/);
    assert.doesNotMatch(markup, /首选投递位置|无回复后尝试|role-proactive-sequence|Agent 模型/);
  });

  it("shows no current mark while the target is unknown", () => {
    const markup = renderToStaticMarkup(
      <RoleProactiveSettingsPanel bindings={[desktop]} channels={null} currentTarget={null} roleForm={{ ...createEmptyRoleForm(), proactiveCandidates: [{ channel: "desktop", chat_id: "role:mira" }] }} onUpdate={() => undefined} />,
    );

    assert.doesNotMatch(markup, /当前/);
  });

  it("checks and unchecks candidates, keeping them in binding order", async () => {
    const state: { form: RoleFormState | undefined } = { form: undefined };
    function Harness() {
      const [form, setForm] = useState<RoleFormState>({ ...createEmptyRoleForm(), channelBindings: [desktop, qqPrivate, qqGroup], proactiveCandidates: [{ channel: "qq", chat_id: "3174898512" }] });
      state.form = form;
      return <RoleProactiveSettingsPanel bindings={form.channelBindings ?? []} channels={[qqChannel]} currentTarget={null} roleForm={form} onUpdate={setForm} />;
    }
    const view = await mountTestComponent(<Harness />);
    try {
      const [desktopBox, , groupBox] = checkboxes(view.container);
      await act(async () => groupBox.click());
      await act(async () => desktopBox.click());
      assert.deepEqual(state.form?.proactiveCandidates, [
        { channel: "desktop", chat_id: "role:mira" },
        { channel: "qq", chat_id: "3174898512" },
        { channel: "qq", chat_id: "gqq:831907794" },
      ]);

      await act(async () => checkboxes(view.container)[1].click());
      assert.deepEqual(state.form?.proactiveCandidates, [
        { channel: "desktop", chat_id: "role:mira" },
        { channel: "qq", chat_id: "gqq:831907794" },
      ]);
    } finally {
      await view.cleanup();
    }
  });
});
