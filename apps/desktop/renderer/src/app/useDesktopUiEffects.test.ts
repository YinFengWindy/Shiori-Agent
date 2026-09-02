/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { shouldWaitForMessageNavigation } from "./useDesktopUiEffects";

describe("shouldWaitForMessageNavigation", () => {
  it("keeps a target pending while its role session is still switching in", () => {
    assert.equal(
      shouldWaitForMessageNavigation(
        { roleId: "mira", messageKey: "role:mira:2" },
        "role:shiori",
        "shiori",
        [],
      ),
      true,
    );
  });

  it("starts DOM navigation once the target role session is active", () => {
    assert.equal(
      shouldWaitForMessageNavigation(
        { roleId: "mira", messageKey: "role:mira:2" },
        "role:mira",
        "mira",
        ["role:mira:2"],
      ),
      false,
    );
  });

  it("keeps navigation pending until the target message is loaded into the session", () => {
    assert.equal(
      shouldWaitForMessageNavigation(
        { roleId: "mira", messageKey: "role:mira:2" },
        "role:mira",
        "mira",
        ["role:mira:199"],
      ),
      true,
    );
  });
});
