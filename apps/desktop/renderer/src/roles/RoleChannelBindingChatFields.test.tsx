import assert from "node:assert/strict";
import { before, describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import type { ChannelSummary } from "../plugins/pluginBridgeClient";
import { changeInputValue, mountTestComponent } from "../shared/testing/domTestHarness";
import { chooseSelectOption } from "../shared/testing/selectTestActions";
import type { RoleChannelBinding } from "../shared/types";

// Base UI's Select only opens its list when first loaded inside a DOM window.
let fields: typeof import("./RoleChannelBindingChatFields");
before(async () => {
  const environment = await mountTestComponent(null);
  fields = await import("./RoleChannelBindingChatFields");
  await environment.cleanup();
});

const qq: ChannelSummary = {
  name: "qq", label: "QQ（NapCat）", contactLabel: "QQ 号",
  chatTypes: [
    { type: "private", label: "私聊", chatIdLabel: "QQ 号", chatIdHint: "对方的 QQ 号", prefix: null },
    { type: "group", label: "群聊", chatIdLabel: "群号", chatIdHint: "QQ 群号", prefix: "gqq:" },
  ],
  pluginId: "qq", pluginEnabled: true, state: "active", error: "", status: null,
};
const qqbot: ChannelSummary = {
  ...qq, name: "qqbot", label: "QQBot",
  chatTypes: [{ type: "private", label: "私聊", chatIdLabel: "用户 OpenID", chatIdHint: null, prefix: "c2c:" }],
};
const group: RoleChannelBinding = { channel: "qq", chat_id: "gqq:831907794", chat_type: "group", blocked_senders: [] };

describe("RoleChannelBindingChatIdField", () => {
  it("shows the number without the type's prefix and writes a pasted internal id back with one prefix", async () => {
    const changes: string[] = [];
    const view = await mountTestComponent(<fields.RoleChannelBindingChatIdField binding={group} channel={qq} readOnly={false} onChange={(chatId) => changes.push(chatId)} />);
    try {
      const input = view.container.querySelector("input");
      assert.ok(input);
      assert.equal(input.value, "831907794");
      assert.equal(input.placeholder, "QQ 群号");
      await changeInputValue(input, "gqq:123");
      await changeInputValue(input, "456");
      assert.deepEqual(changes, ["gqq:123", "gqq:456"]);
    } finally {
      await view.cleanup();
    }
  });

  it("shows the stored chat id read-only when no declaration is available", () => {
    const markup = renderToStaticMarkup(<fields.RoleChannelBindingChatIdField binding={group} channel={null} readOnly={false} onChange={() => undefined} />);

    assert.match(markup, />会话 ID</);
    assert.match(markup, /<input[^>]*readOnly="" value="gqq:831907794"/);
  });

  it("locks the number of a read-only binding", () => {
    const markup = renderToStaticMarkup(<fields.RoleChannelBindingChatIdField binding={group} channel={qq} readOnly onChange={() => undefined} />);

    assert.match(markup, /<input[^>]*readOnly="" value="831907794"/);
  });
});

describe("RoleChannelBindingChatTypeField", () => {
  it("offers the declared types and reports the chosen one", async () => {
    const changes: string[] = [];
    const view = await mountTestComponent(<fields.RoleChannelBindingChatTypeField binding={group} channel={qq} readOnly={false} onChange={(chatType) => changes.push(chatType)} />);
    try {
      await chooseSelectOption("类型", "私聊");
      assert.deepEqual(changes, ["private"]);
    } finally {
      await view.cleanup();
    }
  });

  it("shows a single declared type, a locked binding or a missing declaration read-only", () => {
    const binding: RoleChannelBinding = { channel: "qqbot", chat_id: "c2c:ABC", chat_type: "private", blocked_senders: [] };
    const readOnly = /role="textbox" aria-label="类型" aria-readonly="true">([^<]*)</;

    assert.match(renderToStaticMarkup(<fields.RoleChannelBindingChatTypeField binding={binding} channel={qqbot} readOnly={false} onChange={() => undefined} />), readOnly);
    assert.equal(renderToStaticMarkup(<fields.RoleChannelBindingChatTypeField binding={group} channel={qq} readOnly onChange={() => undefined} />).match(readOnly)?.[1], "群聊");
    assert.equal(renderToStaticMarkup(<fields.RoleChannelBindingChatTypeField binding={group} channel={null} readOnly={false} onChange={() => undefined} />).match(readOnly)?.[1], "群聊");
  });
});
