/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  countHiddenHotChatMessages,
  createHotChatSession,
  ensureHotChatSessionContainsMessage,
  expandHotChatSession,
} from "./chatMessageWindow";
import type { SessionMessage, SessionPayload } from "../shared/types";

function createSession(count: number): SessionPayload {
  return {
    key: "role:mira",
    created_at: "2026-07-07T12:00:00+08:00",
    updated_at: "2026-07-07T12:00:00+08:00",
    last_consolidated: 0,
    metadata: { role_id: "mira" },
    messages: Array.from({ length: count }, (_value, index): SessionMessage => ({
      id: `message-${index + 1}`,
      role: index % 2 === 0 ? "assistant" : "user",
      content: `message-${index + 1}`,
    })),
  };
}

describe("createHotChatSession", () => {
  it("pins the active desktop session to the newest hot message tail", () => {
    const hotSession = createHotChatSession(createSession(240));

    assert.equal(hotSession.messages.length, 160);
    assert.equal(hotSession.messages[0]?.id, "message-81");
    assert.equal(hotSession.messages[159]?.id, "message-240");
  });
});

describe("countHiddenHotChatMessages", () => {
  it("reports how many messages stay in the cold cache outside the hot session", () => {
    const fullSession = createSession(220);
    const hotSession = createHotChatSession(fullSession);

    assert.equal(countHiddenHotChatMessages(fullSession, hotSession), 60);
  });
});

describe("expandHotChatSession", () => {
  it("hydrates one older cold chunk back into the hot session", () => {
    const fullSession = createSession(300);
    const hotSession = createHotChatSession(fullSession);
    const expandedSession = expandHotChatSession(fullSession, hotSession);

    assert.equal(expandedSession.messages.length, 280);
    assert.equal(expandedSession.messages[0]?.id, "message-21");
  });

  it("expands the hot session far enough to include one cold highlighted message", () => {
    const fullSession = createSession(300);
    const hotSession = createHotChatSession(fullSession);
    const expandedSession = ensureHotChatSessionContainsMessage(fullSession, hotSession, "message-40");

    assert.equal(expandedSession.messages.some((message) => message.id === "message-40"), true);
    assert.equal(expandedSession.messages.some((message) => message.id === "message-300"), true);
  });
});
