/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  createRoleSearchResults,
  resolveSearchResultMessageKey,
} from "./roleSearch";
import type { SearchableSessionRecord } from "./appState";
import type { SessionPayload } from "../shared/types";

function createSession(roleId: string, content: string): SessionPayload {
  return {
    key: `role:${roleId}`,
    created_at: "2026-07-04T12:00:00+08:00",
    updated_at: "2026-07-04T12:00:00+08:00",
    last_consolidated: 0,
    metadata: { role_id: roleId },
    messages: [
      {
        id: `${roleId}-message-1`,
        role: "assistant",
        content,
        timestamp: "2026-07-04T12:00:00+08:00",
      },
    ],
  };
}

describe("roleSearch", () => {
  it("builds both role-name and message-content search hits", () => {
    const index: SearchableSessionRecord[] = [
      {
        roleId: "mira",
        roleName: "Mira",
        roleAvatarAbs: null,
        session: createSession("mira", "hello from the archive"),
      },
    ];

    const results = createRoleSearchResults(index, "mir");

    assert.equal(results[0]?.matchedField, "role");
    assert.match(results[0]?.matchedMessagePreview ?? "", /角色 Mira/);
  });

  it("falls back to role-and-index keys when a message id is missing", () => {
    const activeSession = createSession("mira", "hello");
    activeSession.messages[0].id = undefined;
    const searchIndex: SearchableSessionRecord[] = [
      {
        roleId: "mira",
        roleName: "Mira",
        roleAvatarAbs: null,
        session: activeSession,
      },
    ];

    const messageKey = resolveSearchResultMessageKey({
      roleId: "mira",
      messageId: null,
      messageIndex: 0,
      activeRoleId: "mira",
      activeSession,
      searchIndex,
    });

    assert.equal(messageKey, "assistant-0");
  });

  it("falls back to the indexed full session when the current hot session no longer contains the hit index", () => {
    const indexedSession: SessionPayload = {
      ...createSession("mira", "older"),
      messages: [
        {
          id: undefined,
          role: "assistant",
          content: "older",
        },
        {
          id: "mira-message-2",
          role: "assistant",
          content: "newer",
        },
      ],
    };
    const activeSession: SessionPayload = {
      ...indexedSession,
      messages: [indexedSession.messages[1]],
    };
    const searchIndex: SearchableSessionRecord[] = [
      {
        roleId: "mira",
        roleName: "Mira",
        roleAvatarAbs: null,
        session: indexedSession,
      },
    ];

    const messageKey = resolveSearchResultMessageKey({
      roleId: "mira",
      messageId: null,
      messageIndex: 0,
      activeRoleId: "mira",
      activeSession,
      searchIndex,
    });

    assert.equal(messageKey, "assistant-0");
  });
});
