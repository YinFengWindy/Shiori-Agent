/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { mergeIncomingSessionDuringSend } from "../chat/chatSessionMerge";
import {
  canSendSessionState,
  clearAllSendingSessionsState,
  clearSendingSessionState,
  markSendingSessionState,
} from "./useDesktopSessionState";
import type { SessionMessage, SessionPayload } from "../shared/types";

function createSession(messages: SessionMessage[]): SessionPayload {
  return {
    key: "role:shiori",
    created_at: "2026-07-06T12:00:00+08:00",
    updated_at: "2026-07-06T12:00:00+08:00",
    last_consolidated: 0,
    metadata: { role_id: "shiori" },
    messages,
  };
}

describe("markSendingSessionState", () => {
  it("marks the session as sending before a stale session snapshot is merged", () => {
    const currentSession = createSession([
      {
        id: "role:shiori:1",
        role: "assistant",
        content: "上一条消息",
      },
      {
        role: "user",
        content: "刚发出去的消息",
      },
    ]);
    const incomingSession = createSession([
      {
        id: "role:shiori:1",
        role: "assistant",
        content: "上一条消息",
      },
    ]);

    const sendingSessions = markSendingSessionState({}, currentSession.key, "shiori");
    const merged = mergeIncomingSessionDuringSend(
      currentSession,
      incomingSession,
      Boolean(sendingSessions[currentSession.key]),
    );

    assert.deepEqual(merged?.messages, currentSession.messages);
  });
});

describe("clearSendingSessionState", () => {
  it("removes only the finished session from the sending map", () => {
    assert.deepEqual(
      clearSendingSessionState(
        {
          "role:shiori": "shiori",
          "role:other": "other",
        },
        "role:shiori",
      ),
      {
        "role:other": "other",
      },
    );
  });
});

describe("clearAllSendingSessionsState", () => {
  it("clears the sending map once bridge sending state is reset", () => {
    assert.deepEqual(
      clearAllSendingSessionsState({
        "role:shiori": "shiori",
      }),
      {},
    );
  });
});

describe("canSendSessionState", () => {
  it("allows sending in a different role session while another role is still replying", () => {
    assert.equal(
      canSendSessionState(
        {
          "role:shiori": "shiori",
        },
        "role:mira",
      ),
      true,
    );
  });

  it("blocks sending only for the in-flight session itself", () => {
    assert.equal(
      canSendSessionState(
        {
          "role:shiori": "shiori",
        },
        "role:shiori",
      ),
      false,
    );
  });
});
