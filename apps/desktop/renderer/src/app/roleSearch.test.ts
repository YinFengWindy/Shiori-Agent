/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  createRoleSearchResults,
  parseRoleSearchMessageResults,
  resolveSearchResultMessageKey,
  resolveRoleSearchMessageResults,
} from "./roleSearch";
import type { RoleRecord, SessionSearchResult } from "../shared/types";

const roles = [{
  id: "mira",
  name: "Mira",
  avatar_abs: "C:\\roles\\mira.png",
}] as RoleRecord[];

describe("roleSearch", () => {
  it("combines local role-name matches with backend FTS hits", () => {
    const results = createRoleSearchResults(roles, [{
      id: "role:mira:42",
      session_key: "role:mira",
      seq: 42,
      role: "assistant",
      preview: "archive memory about the starlight station",
      timestamp: "2026-07-04T12:00:00+08:00",
    }] satisfies SessionSearchResult[], "mir");

    assert.deepEqual(results, [{
      roleId: "mira",
      roleName: "Mira",
      roleAvatarAbs: "C:\\roles\\mira.png",
      sessionKey: "role:mira",
      matchedMessageTimestamp: null,
      matchedMessageId: null,
      matchedMessageIndex: null,
      matchedMessagePreview: "角色 Mira",
      matchedField: "role",
    }, {
      roleId: "mira",
      roleName: "Mira",
      roleAvatarAbs: "C:\\roles\\mira.png",
      sessionKey: "role:mira",
      matchedMessageTimestamp: "2026-07-04T12:00:00+08:00",
      matchedMessageId: "role:mira:42",
      matchedMessageIndex: null,
      matchedMessagePreview: "archive memory about the starlight station",
      matchedField: "message",
    }]);
  });

  it("uses a backend message id directly as the navigation key", () => {
    assert.equal(resolveSearchResultMessageKey("role:mira:42"), "role:mira:42");
    assert.equal(resolveSearchResultMessageKey(null), "");
  });

  it("returns no message hits for a malformed bridge payload", () => {
    assert.deepEqual(parseRoleSearchMessageResults({ results: [{
      id: "role:mira:42",
      session_key: "role:mira",
      seq: "42",
      role: "assistant",
      preview: "malformed sequence",
      timestamp: "2026-07-04T12:00:00+08:00",
    }] }), []);
    assert.deepEqual(parseRoleSearchMessageResults({}), []);
  });

  it("clears message hits when the bridge returns an error", () => {
    const payload = {
      results: [{
        id: "role:mira:42",
        session_key: "role:mira",
        seq: 42,
        role: "assistant",
        preview: "previous query hit",
        timestamp: "2026-07-04T12:00:00+08:00",
      }],
    };

    assert.deepEqual(
      resolveRoleSearchMessageResults(payload, { message: "bridge unavailable" }),
      [],
    );
  });
});
