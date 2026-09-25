import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import type { ChannelSummary } from "../plugins/pluginBridgeClient";
import {
  changeRoleBindingChatType,
  composeRoleBindingChatId,
  defaultRoleChatType,
  findRoleChatType,
  roleBindingDisplayLabel,
  roleBindingNumber,
  roleChatTypeOptions,
} from "./roleChatTypes";

const qq: ChannelSummary = {
  name: "qq", label: "QQ（NapCat）", contactLabel: "QQ 号", chatIdLabel: null, chatIdHint: null,
  chatTypes: [
    { type: "private", label: "私聊", chatIdLabel: "QQ 号", chatIdHint: null, prefix: null },
    { type: "group", label: "群聊", chatIdLabel: "群号", chatIdHint: null, prefix: "gqq:" },
  ],
  pluginId: "qq", pluginEnabled: true, state: "active", error: "", status: null,
};
const telegram: ChannelSummary = { ...qq, name: "telegram", label: "Telegram", chatTypes: [] };
const group = findRoleChatType(qq, "group");

describe("roleChatTypes", () => {
  it("finds declared types and defaults new bindings to the first one", () => {
    assert.equal(group?.prefix, "gqq:");
    assert.equal(findRoleChatType(telegram, "group"), null);
    assert.equal(defaultRoleChatType(qq), "private");
    assert.equal(defaultRoleChatType({ ...qq, chatTypes: [qq.chatTypes[1]] }), "group");
    assert.equal(defaultRoleChatType(null), "private");
    assert.deepEqual(roleChatTypeOptions(qq), [{ value: "private", label: "私聊" }, { value: "group", label: "群聊" }]);
  });

  it("splits the prefix off for display and composes it back on input", () => {
    assert.equal(roleBindingNumber("gqq:831907794", group), "831907794");
    assert.equal(roleBindingNumber("831907794", null), "831907794");
    assert.equal(composeRoleBindingChatId(" 831907794 ", group), "gqq:831907794");
    // Clearing the number must not leave a bare prefix behind.
    assert.equal(composeRoleBindingChatId("  ", group), "");
    assert.equal(composeRoleBindingChatId("-1001", null), "-1001");
  });

  it("re-derives the prefix when the session type changes", () => {
    const binding = { channel: "qq", chat_id: "gqq:831907794", chat_type: "group" as const, allow_from: ["3"] };

    assert.deepEqual(changeRoleBindingChatType(binding, qq, "private"), { ...binding, chat_id: "831907794", chat_type: "private" });
  });

  it("labels bindings by type and number, falling back to the raw chat id", () => {
    const catalog = [qq, telegram];

    assert.equal(roleBindingDisplayLabel({ channel: "qq", chat_id: "gqq:831907794", chat_type: "group", allow_from: [] }, catalog), "QQ（NapCat） · 群聊 831907794");
    assert.equal(roleBindingDisplayLabel({ channel: "qq", chat_id: "3174898512", chat_type: "private", allow_from: [] }, catalog), "QQ（NapCat） · 私聊 3174898512");
    assert.equal(roleBindingDisplayLabel({ channel: "telegram", chat_id: "-1001", chat_type: "group", allow_from: [] }, catalog), "Telegram · -1001");
    assert.equal(roleBindingDisplayLabel({ channel: "qq", chat_id: "gqq:1", chat_type: "group", allow_from: [] }, null), "qq · gqq:1");
  });
});
