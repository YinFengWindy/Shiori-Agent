/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { SessionMessage, SessionPayload, SessionSummary } from "../shared/types";
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

function summary(key: string): SessionSummary {
  const { messages: _messages, ...sessionSummary } = session(key, "");
  return sessionSummary;
}

function regeneratedMessage(key: string, imagePath: string): SessionMessage {
  return { id: `${key}:1`, seq: 1, role: "assistant", content: "scene", media: [imagePath] };
}

describe("applyRegeneratedSession", () => {
  it("updates the original session without requiring any image-selection change", () => {
    const regenerated = regeneratedMessage("role:mira", "new.png");

    assert.deepEqual(
      applyRegeneratedSession(
        session("role:mira", "old.png"),
        "role:mira",
        summary("role:mira"),
        regenerated,
      )?.messages,
      [regenerated],
    );
  });

  it("does not overwrite the session opened while generation was running", () => {
    const current = session("role:atlas", "atlas.png");

    assert.equal(
      applyRegeneratedSession(
        current,
        "role:mira",
        summary("role:mira"),
        regeneratedMessage("role:mira", "new.png"),
      ),
      current,
    );
  });
});
