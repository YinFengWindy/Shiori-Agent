/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  getRoleIdFromSession,
  isProactiveAssistantMessage,
  navigationEntriesEqual,
} from "./appState";
import type { NavigationEntry } from "./appState";
import type { SessionPayload } from "../shared/types";

function createSession(overrides: Partial<SessionPayload> = {}): SessionPayload {
  return {
    key: overrides.key ?? "role:mira",
    created_at: overrides.created_at ?? "2026-07-04T12:00:00+08:00",
    updated_at: overrides.updated_at ?? "2026-07-04T12:00:00+08:00",
    last_consolidated: overrides.last_consolidated ?? 0,
    metadata: overrides.metadata ?? {},
    messages: overrides.messages ?? [],
  };
}

describe("appState", () => {
  it("prefers the explicit metadata role id when resolving a session role", () => {
    const session = createSession({
      key: "role:stale",
      metadata: { role_id: "mira" },
    });

    assert.equal(getRoleIdFromSession(session), "mira");
  });

  it("matches navigation entries only when view, role, and settings section all align", () => {
    const baseEntry: NavigationEntry = {
      view: { kind: "role-detail", roleId: "mira" },
      activeRoleId: "mira",
      settingsSection: "models",
    };

    assert.equal(navigationEntriesEqual(baseEntry, baseEntry), true);
    assert.equal(navigationEntriesEqual(baseEntry, {
      ...baseEntry,
      settingsSection: "integrations",
    }), false);
  });

  it("recognizes proactive assistant pushes from the latest assistant message", () => {
    const proactiveSession = createSession({
      messages: [
        {
          role: "assistant",
          content: "hi",
          metadata: { proactive: true },
        },
      ],
    });
    const passiveSession = createSession({
      messages: [
        {
          role: "user",
          content: "hi",
        },
      ],
    });

    assert.equal(isProactiveAssistantMessage(proactiveSession), true);
    assert.equal(isProactiveAssistantMessage(passiveSession), false);
  });
});
