/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  readRoleSessionCache,
  removeRoleSessionCache,
  resolveImmediateRoleSession,
  retainRoleSessionCache,
  writeRoleSessionCache,
  type RoleSessionCache,
} from "./roleSessionCache";
import type { SessionPayload } from "../shared/types";

function createSession(roleId: string, updatedAt: string): SessionPayload {
  return {
    key: `role:${roleId}`,
    created_at: updatedAt,
    updated_at: updatedAt,
    last_consolidated: 0,
    metadata: { role_id: roleId },
    messages: [
      {
        id: `${roleId}-message-1`,
        role: "assistant",
        content: `${roleId} session`,
        timestamp: updatedAt,
      },
    ],
  };
}

describe("roleSessionCache", () => {
  it("reads a cached session even when the role id contains surrounding spaces", () => {
    const session = createSession("mira", "2026-07-04T10:00:00+08:00");
    const cache = writeRoleSessionCache({}, "mira", session);

    assert.equal(readRoleSessionCache(cache, "  mira  "), session);
  });

  it("preserves the same cache object when writing the identical session reference", () => {
    const session = createSession("mira", "2026-07-04T10:00:00+08:00");
    const cache = writeRoleSessionCache({}, "mira", session);

    assert.equal(writeRoleSessionCache(cache, "mira", session), cache);
  });

  it("drops the previous role session immediately when switching to a role without cache", () => {
    const currentSession = createSession("mira", "2026-07-04T10:00:00+08:00");

    const immediateSession = resolveImmediateRoleSession({
      currentRoleId: "mira",
      nextRoleId: "luna",
      currentSession,
      cachedSession: null,
    });

    assert.equal(immediateSession, null);
  });

  it("shows only the cached hot tail immediately when switching to another cached role", () => {
    const cachedSession: SessionPayload = {
      ...createSession("luna", "2026-07-04T10:05:00+08:00"),
      messages: Array.from({ length: 220 }, (_value, index) => ({
        id: `luna-message-${index + 1}`,
        role: index % 2 === 0 ? "assistant" : "user",
        content: `message-${index + 1}`,
      })),
    };

    const immediateSession = resolveImmediateRoleSession({
      currentRoleId: "mira",
      nextRoleId: "luna",
      currentSession: createSession("mira", "2026-07-04T10:00:00+08:00"),
      cachedSession,
    });

    assert.equal(immediateSession?.messages.length, 160);
    assert.equal(immediateSession?.messages[0]?.id, "luna-message-61");
  });

  it("removes a deleted role and prunes sessions for roles that no longer exist", () => {
    const cache: RoleSessionCache = {
      mira: createSession("mira", "2026-07-04T10:00:00+08:00"),
      luna: createSession("luna", "2026-07-04T10:01:00+08:00"),
      stale: createSession("stale", "2026-07-04T10:02:00+08:00"),
    };

    const removedCache = removeRoleSessionCache(cache, "luna");
    const retainedCache = retainRoleSessionCache(removedCache, ["mira"]);

    assert.deepEqual(Object.keys(retainedCache), ["mira"]);
    assert.equal(readRoleSessionCache(retainedCache, "mira")?.key, "role:mira");
    assert.equal(readRoleSessionCache(retainedCache, "luna"), null);
    assert.equal(readRoleSessionCache(retainedCache, "stale"), null);
  });
});
