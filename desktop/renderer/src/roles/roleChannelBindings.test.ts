import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import {
  buildProactiveTransportSequence,
  changeRoleBindingChannel,
  createRoleChannelBinding,
  moveRoleChannelBinding,
  roleBindingAllowFromLabel,
} from "./roleChannelBindings";

describe("roleChannelBindings", () => {
  it("uses the owning role session for desktop bindings", () => {
    assert.deepEqual(createRoleChannelBinding("mira", "desktop"), {
      channel: "desktop",
      chat_id: "role:mira",
      allow_from: [],
    });
  });

  it("clears the desktop session id when changing back to an external channel", () => {
    assert.deepEqual(
      changeRoleBindingChannel(
        { channel: "desktop", chat_id: "role:mira", allow_from: [] },
        "telegram",
        "mira",
      ),
      { channel: "telegram", chat_id: "", allow_from: [] },
    );
  });

  it("explains each external channel's supported allow-list identity", () => {
    assert.match(roleBindingAllowFromLabel("telegram"), /用户 ID 或用户名/);
    assert.match(roleBindingAllowFromLabel("qq"), /QQ 号/);
  });

  it("moves bindings in either direction without mutating the source array", () => {
    const bindings = [
      { channel: "telegram", chat_id: "100", allow_from: [] },
      { channel: "qq", chat_id: "200", allow_from: [] },
      { channel: "desktop", chat_id: "role:mira", allow_from: [] },
    ];

    assert.deepEqual(moveRoleChannelBinding(bindings, 1, "up"), [bindings[1], bindings[0], bindings[2]]);
    assert.deepEqual(moveRoleChannelBinding(bindings, 1, "down"), [bindings[0], bindings[2], bindings[1]]);
    assert.deepEqual(bindings, [
      { channel: "telegram", chat_id: "100", allow_from: [] },
      { channel: "qq", chat_id: "200", allow_from: [] },
      { channel: "desktop", chat_id: "role:mira", allow_from: [] },
    ]);
  });

  it("keeps bindings unchanged when moving beyond either end", () => {
    const bindings = [{ channel: "telegram", chat_id: "100", allow_from: [] }];

    assert.strictEqual(moveRoleChannelBinding(bindings, 0, "up"), bindings);
    assert.strictEqual(moveRoleChannelBinding(bindings, 0, "down"), bindings);
  });

  it("puts the preferred target first and keeps other targets in binding order", () => {
    const bindings = [
      { channel: "telegram", chat_id: "100", allow_from: [] },
      { channel: "qq", chat_id: "200", allow_from: [] },
      { channel: "desktop", chat_id: "role:mira", allow_from: [] },
      { channel: "telegram", chat_id: "", allow_from: [] },
    ];

    assert.deepEqual(
      buildProactiveTransportSequence(bindings, "qq", "200").map(({ channel, chat_id }) => `${channel}:${chat_id}`),
      ["qq:200", "telegram:100", "desktop:role:mira"],
    );
  });
});
