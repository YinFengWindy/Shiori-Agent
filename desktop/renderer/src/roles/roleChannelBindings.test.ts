import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
import {
  changeRoleBindingChannel,
  createRoleChannelBinding,
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
});
