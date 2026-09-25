import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import type { ChannelSummary } from "../plugins/pluginBridgeClient";
import type { RoleChannelBinding } from "../shared/types";
import {
  buildProactiveTransportSequence,
  changeRoleBindingChannel,
  createRoleChannelBinding,
  moveRoleChannelBinding,
} from "./roleChannelBindings";

function channel(name: string, chatTypes: ChannelSummary["chatTypes"]): ChannelSummary {
  return { name, label: name, contactLabel: null, chatIdLabel: null, chatIdHint: null, chatTypes, pluginId: name, pluginEnabled: true, state: "active", error: "", status: null };
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
      allow_from: [],
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
        { channel: "desktop", chat_id: "role:mira", chat_type: "private", allow_from: [] },
        "telegram",
        "mira",
        catalog,
      ),
      { channel: "telegram", chat_id: "", chat_type: "private", allow_from: [] },
    );
  });

  it("keeps the entered number but not the old type's prefix when changing channel", () => {
    const group: RoleChannelBinding = { channel: "qq", chat_id: "gqq:831907794", chat_type: "group", allow_from: ["3"] };

    assert.deepEqual(changeRoleBindingChannel(group, "qqbot", "mira", catalog), {
      channel: "qqbot", chat_id: "c2c:831907794", chat_type: "private", allow_from: ["3"],
    });
    assert.deepEqual(changeRoleBindingChannel(group, "telegram", "mira", catalog), {
      channel: "telegram", chat_id: "831907794", chat_type: "private", allow_from: ["3"],
    });
  });

  it("moves bindings in either direction without mutating the source array", () => {
    const bindings: RoleChannelBinding[] = [
      { channel: "telegram", chat_id: "100", chat_type: "private", allow_from: [] },
      { channel: "qq", chat_id: "200", chat_type: "private", allow_from: [] },
      { channel: "desktop", chat_id: "role:mira", chat_type: "private", allow_from: [] },
    ];

    assert.deepEqual(moveRoleChannelBinding(bindings, 1, "up"), [bindings[1], bindings[0], bindings[2]]);
    assert.deepEqual(moveRoleChannelBinding(bindings, 1, "down"), [bindings[0], bindings[2], bindings[1]]);
    assert.deepEqual(bindings, [
      { channel: "telegram", chat_id: "100", chat_type: "private", allow_from: [] },
      { channel: "qq", chat_id: "200", chat_type: "private", allow_from: [] },
      { channel: "desktop", chat_id: "role:mira", chat_type: "private", allow_from: [] },
    ]);
  });

  it("keeps bindings unchanged when moving beyond either end", () => {
    const bindings: RoleChannelBinding[] = [{ channel: "telegram", chat_id: "100", chat_type: "private", allow_from: [] }];

    assert.strictEqual(moveRoleChannelBinding(bindings, 0, "up"), bindings);
    assert.strictEqual(moveRoleChannelBinding(bindings, 0, "down"), bindings);
  });

  it("puts the preferred target first and keeps other targets in binding order", () => {
    const bindings: RoleChannelBinding[] = [
      { channel: "telegram", chat_id: "100", chat_type: "private", allow_from: [] },
      { channel: "qq", chat_id: "200", chat_type: "private", allow_from: [] },
      { channel: "desktop", chat_id: "role:mira", chat_type: "private", allow_from: [] },
      { channel: "telegram", chat_id: "", chat_type: "private", allow_from: [] },
    ];

    assert.deepEqual(
      buildProactiveTransportSequence(bindings, "qq", "200").map(({ channel, chat_id }) => `${channel}:${chat_id}`),
      ["qq:200", "telegram:100", "desktop:role:mira"],
    );
  });
});
