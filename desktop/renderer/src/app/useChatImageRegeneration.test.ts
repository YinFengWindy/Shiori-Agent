/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { SessionPayload } from "../shared/types";
import { applyRegeneratedSession } from "./useChatImageRegeneration";

function session(key: string, imagePath: string): SessionPayload {
  return {
    key,
    created_at: "2026-07-22T08:00:00+00:00",
    updated_at: "2026-07-22T08:00:00+00:00",
    last_consolidated: 0,
    metadata: {},
    messages: [{ id: `${key}:1`, role: "assistant", content: "scene", media: [imagePath] }],
  };
}

describe("applyRegeneratedSession", () => {
  it("updates the original session without requiring any image-selection change", () => {
    const regenerated = session("role:mira", "new.png");

    assert.equal(
      applyRegeneratedSession(session("role:mira", "old.png"), "role:mira", regenerated),
      regenerated,
    );
  });

  it("does not overwrite the session opened while generation was running", () => {
    const current = session("role:atlas", "atlas.png");

    assert.equal(
      applyRegeneratedSession(current, "role:mira", session("role:mira", "new.png")),
      current,
    );
  });
});
