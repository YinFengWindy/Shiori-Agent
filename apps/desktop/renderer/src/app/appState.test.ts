/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  cloneView,
  getRoleIdFromSession,
  isProactiveAssistantMessage,
  navigationEntriesEqual,
  viewsEqual,
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

  it("matches navigation entries only when view, role, settings section and subtab all align", () => {
    const baseEntry: NavigationEntry = {
      view: { kind: "role-detail", roleId: "mira" },
      activeRoleId: "mira",
      settingsSection: "models",
      settingsSubsection: "catalog",
    };

    assert.equal(navigationEntriesEqual(baseEntry, baseEntry), true);
    assert.equal(navigationEntriesEqual(baseEntry, {
      ...baseEntry,
      settingsSection: "integrations",
    }), false);
    assert.equal(navigationEntriesEqual(baseEntry, {
      ...baseEntry,
      settingsSubsection: "other",
    }), false);
  });

  it("treats a plugin page as a distinct history destination", () => {
    const pluginPageEntry: NavigationEntry = {
      view: { kind: "plugin-page", pageId: "sample" },
      activeRoleId: "mira",
      settingsSection: "models",
      settingsSubsection: "catalog",
    };

    assert.equal(navigationEntriesEqual(pluginPageEntry, { ...pluginPageEntry, view: { kind: "plugin-page", pageId: "sample" } }), true);
    assert.equal(navigationEntriesEqual(pluginPageEntry, { ...pluginPageEntry, view: { kind: "chat" } }), false);
    assert.deepEqual(cloneView(pluginPageEntry.view), { kind: "plugin-page", pageId: "sample" });
    assert.equal(viewsEqual(pluginPageEntry.view, { kind: "chat" }), false);
  });

  it("distinguishes plugin nav pages by their page id", () => {
    const pluginEntry: NavigationEntry = {
      view: { kind: "plugin-page", pageId: "demo" },
      activeRoleId: "mira",
      settingsSection: "models",
      settingsSubsection: "catalog",
    };

    assert.deepEqual(cloneView(pluginEntry.view), { kind: "plugin-page", pageId: "demo" });
    assert.equal(viewsEqual(pluginEntry.view, { kind: "plugin-page", pageId: "demo" }), true);
    assert.equal(viewsEqual(pluginEntry.view, { kind: "plugin-page", pageId: "other" }), false);
    assert.equal(viewsEqual(pluginEntry.view, { kind: "chat" }), false);
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
