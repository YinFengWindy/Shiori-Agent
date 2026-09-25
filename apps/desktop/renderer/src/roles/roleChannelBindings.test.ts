import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import type { ChannelSummary } from "../plugins/pluginBridgeClient";
import type { RoleChannelBinding } from "../shared/types";
import {
  changeRoleBindingChannel,
  createRoleChannelBinding,
} from "./roleChannelBindings";

function channel(name: string, chatTypes: ChannelSummary["chatTypes"]): ChannelSummary {
  return { name, label: name, contactLabel: null, chatTypes, pluginId: name, pluginEnabled: true, state: "active", error: "", status: null };
}

const qq = channel("qq", [
  { type: "private", label: "私聊", chatIdLabel: "QQ 号", chatIdHint: null, prefix: null },
  { type: "group", label: "群聊", chatIdLabel: "群号", chatIdHint: null, prefix: "gqq:" },
]);
const qqbot = channel("qqbot", [{ type: "private", label: "私聊", chatIdLabel: "用户 OpenID", chatIdHint: null, prefix: "c2c:" }]);
const catalog = [qq, qqbot, channel("telegram", [])];

describe("roleChannelBindings", () => {
  it("uses the owning role session for desktop bindings", () => {
    assert.deepEqual(createRoleChannelBinding("mira", "desktop", catalog), {
      channel: "desktop",
      chat_id: "role:mira",
      chat_type: "private",
      blocked_senders: [],
    });
  });

  it("types a new binding as the channel's first declared session type", () => {
    assert.equal(createRoleChannelBinding("mira", "qqbot", catalog).chat_type, "private");
    assert.equal(createRoleChannelBinding("mira", "telegram", catalog).chat_type, "private");
    assert.equal(createRoleChannelBinding("mira", "qq", null).chat_type, "private");
  });

  it("clears the desktop session id when changing back to an external channel", () => {
    assert.deepEqual(
      changeRoleBindingChannel(
        { channel: "desktop", chat_id: "role:mira", chat_type: "private", blocked_senders: [] },
        "telegram",
        "mira",
        catalog,
      ),
      { channel: "telegram", chat_id: "", chat_type: "private", blocked_senders: [] },
    );
  });

  it("keeps the entered number but neither the old type's prefix nor the blacklist when changing channel", () => {
    const group: RoleChannelBinding = { channel: "qq", chat_id: "gqq:831907794", chat_type: "group", blocked_senders: ["3"] };

    assert.deepEqual(changeRoleBindingChannel(group, "qqbot", "mira", catalog), {
      channel: "qqbot", chat_id: "c2c:831907794", chat_type: "private", blocked_senders: [],
    });
    assert.deepEqual(changeRoleBindingChannel(group, "telegram", "mira", catalog), {
      channel: "telegram", chat_id: "831907794", chat_type: "private", blocked_senders: [],
    });
  });
});
