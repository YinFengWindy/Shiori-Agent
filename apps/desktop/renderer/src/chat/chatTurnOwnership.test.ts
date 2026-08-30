/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  isActiveChatTurn,
  shouldSurfaceChatCancellationFailure,
} from "./chatTurnOwnership";

describe("chat turn ownership", () => {
  it("rejects a late event from a cancelled turn after the session starts a replacement turn", () => {
    const activeTurns = { "role:mira": "turn-b" };

    assert.equal(isActiveChatTurn(activeTurns, "role:mira", "turn-a"), false);
    assert.equal(isActiveChatTurn(activeTurns, "role:mira", "turn-b"), true);
  });

  it("requires both the session key and turn id to match", () => {
    const activeTurns = { "role:mira": "turn-a" };

    assert.equal(isActiveChatTurn(activeTurns, "role:other", "turn-a"), false);
    assert.equal(isActiveChatTurn(activeTurns, "role:mira", ""), false);
  });

  it("does not surface a stale cancellation failure after the turn has already completed", () => {
    assert.equal(shouldSurfaceChatCancellationFailure({}, "role:mira", "turn-a"), false);
    assert.equal(
      shouldSurfaceChatCancellationFailure({ "role:mira": "turn-a" }, "role:mira", "turn-a"),
      true,
    );
  });
});
