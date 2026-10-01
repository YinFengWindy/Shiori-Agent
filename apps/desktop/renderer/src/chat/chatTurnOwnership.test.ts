/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { matchesChatTurn } from "./chatTurnOwnership";

describe("chat turn ownership", () => {
  it("rejects a late event from a cancelled turn after the session starts a replacement turn", () => {
    const activeTurns = { "role:mira": "turn-b" };

    assert.equal(matchesChatTurn(activeTurns, "role:mira", "turn-a"), false);
    assert.equal(matchesChatTurn(activeTurns, "role:mira", "turn-b"), true);
  });

  it("requires both the session key and turn id to match", () => {
    const activeTurns = { "role:mira": "turn-a" };

    assert.equal(matchesChatTurn(activeTurns, "role:other", "turn-a"), false);
    assert.equal(matchesChatTurn(activeTurns, "role:mira", ""), false);
  });
});
