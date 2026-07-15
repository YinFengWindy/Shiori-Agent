import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type { RoleRecord, SessionPayload } from "../shared/types";
import { chooseRoleIllustration } from "./useRolePresentation";

const role = {
  illustrations_abs: ["C:\\roles\\mira\\happy.png", "C:\\roles\\mira\\calm.png"],
  chat_background_abs: "C:\\roles\\mira\\calm.png",
} as RoleRecord;

function createSession(activeIllustration: string): SessionPayload {
  return {
    key: "role:mira",
    created_at: "2026-07-15T00:00:00Z",
    updated_at: "2026-07-15T00:00:00Z",
    last_consolidated: 0,
    metadata: { active_illustration: activeIllustration },
    messages: [],
  };
}

describe("chooseRoleIllustration", () => {
  it("prefers a valid session illustration", () => {
    const session = createSession("C:\\roles\\mira\\happy.png");

    assert.equal(
      chooseRoleIllustration(role, session, "C:\\roles\\mira\\calm.png"),
      "C:\\roles\\mira\\happy.png",
    );
  });

  it("rejects paths outside the role assets and falls back to the chat background", () => {
    const session = createSession("C:\\outside\\forged.png");

    assert.equal(
      chooseRoleIllustration(role, session, "C:\\outside\\fallback.png"),
      "C:\\roles\\mira\\calm.png",
    );
  });
});
