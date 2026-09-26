/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type React from "react";
import type { BridgeResponse } from "../../../src/bridge/shared";
import type { AppMainView, NewRoleFormState, PendingRoleCardAction, RoleRecord } from "../shared/types";
import type { NavigationEntry } from "./appState";
import { createFeedbackRecorder } from "../shared/testing/feedbackRecorder";
import {
  cancelRoleCreation,
  resetRoleCreationForm,
  runRoleCreation,
  type RoleCreationWorkflowArgs,
} from "./roleCreationWorkflow";

function createRole(overrides: Partial<RoleRecord> = {}): RoleRecord {
  return {
    id: overrides.id ?? "mira",
    name: overrides.name ?? "Mira",
    description: overrides.description ?? "A role",
    system_prompt: overrides.system_prompt ?? "Be helpful",
    runtime_config: overrides.runtime_config ?? {},
    channel_bindings: overrides.channel_bindings ?? [],
    proactive: overrides.proactive,
    avatar: overrides.avatar ?? null,
    avatar_abs: overrides.avatar_abs ?? null,
    chat_background: overrides.chat_background ?? null,
    chat_background_abs: overrides.chat_background_abs ?? null,
    illustrations: overrides.illustrations ?? [],
    illustrations_abs: overrides.illustrations_abs ?? [],
    asset_categories: overrides.asset_categories ?? [{ id: "default", name: "Default", allow_role_send: false }],
    asset_category_bindings: overrides.asset_category_bindings ?? {},
    created_at: overrides.created_at ?? "2026-08-30T00:00:00Z",
    updated_at: overrides.updated_at ?? "2026-08-30T00:00:00Z",
  };
}

function createForm(overrides: Partial<NewRoleFormState> = {}): NewRoleFormState {
  return {
    name: overrides.name ?? "  Mira  ",
    description: overrides.description ?? "A role",
    systemPrompt: overrides.systemPrompt ?? "  Be helpful  ",
    profile: overrides.profile,
    importId: overrides.importId,
    emotionSelections: overrides.emotionSelections,
  };
}

function createResponse(payload: Record<string, unknown> = {}, error: BridgeResponse["error"] = null): BridgeResponse {
  return { id: "request-1", type: "response", method: "roles.create", payload, error };
}

function createHarness({
  invoke = async () => createResponse({ role: createRole() }),
  loadedRoles = [createRole()],
}: {
  invoke?: (request: { method: string; payload: Record<string, unknown> }) => Promise<BridgeResponse>;
  loadedRoles?: RoleRecord[] | null;
} = {}) {
  let roles = [createRole({ id: "existing", name: "Existing" })];
  let activeRoleId = "existing";
  let creating = false;
  let pendingAction: PendingRoleCardAction = null;
  const feedback = createFeedbackRecorder();
  const activeRoleIdRef = { current: activeRoleId };
  const views: AppMainView[] = [];
  const navigationEntries: NavigationEntry[] = [];
  const snapshots: RoleRecord[] = [];
  const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
  const openedRoles: string[] = [];
  const openedSnapshots: Array<RoleRecord | null | undefined> = [];
  let refreshCount = 0;

  const apply = <T>(current: T, next: T | ((value: T) => T)): T => (
    typeof next === "function" ? (next as (value: T) => T)(current) : next
  );

  const args: RoleCreationWorkflowArgs = {
      activeRoleIdRef,
      setPendingRoleCardAction: (next: React.SetStateAction<PendingRoleCardAction>) => { pendingAction = apply(pendingAction, next); },
      feedback: feedback.reporter,
      setRoles: (next: React.SetStateAction<RoleRecord[]>) => { roles = apply(roles, next); },
      setActiveRoleId: (next: React.SetStateAction<string>) => { activeRoleId = apply(activeRoleId, next); },
      openRoleWorkspace: (view: Extract<AppMainView, { kind: "roles-list" | "role-create" | "role-detail" | "role-assets" }>) => { views.push(view); },
      buildNavigationEntry: (view: AppMainView, roleId = "") => ({ view, activeRoleId: roleId, settingsSection: "models" as const, settingsSubsection: "" }),
      replaceNavigationEntry: (entry: NavigationEntry) => { navigationEntries.push(entry); },
      loadRolesFromBridge: async () => { refreshCount += 1; return loadedRoles; },
      openRole: async (roleId: string, role?: RoleRecord | null) => { openedRoles.push(roleId); openedSnapshots.push(role); return true; },
      applyRoleSnapshot: (role: RoleRecord) => { snapshots.push(role); },
      setCreating: (next: React.SetStateAction<boolean>) => { creating = apply(creating, next); },
      invoke: async (request: { method: string; payload: Record<string, unknown> }) => { requests.push(request); return invoke(request); },
      waitForBusy: async () => undefined,
      createPendingRoleId: () => "pending-create:test",
  };

  return {
    args,
    get state() {
      return { roles, activeRoleId, activeRoleIdRef, creating, pendingAction, feedback: feedback.last, views, navigationEntries, snapshots, requests, openedRoles, openedSnapshots, refreshCount };
    },
  };
}

describe("runRoleCreation", () => {
  it("validates required fields before calling the bridge", async () => {
    const harness = createHarness();

    const created = await runRoleCreation(
      createForm({ name: " ", systemPrompt: "" }),
      harness.args,
    );

    assert.equal(created, false);
    assert.equal(harness.state.requests.length, 0);
    assert.equal(harness.state.roles.length, 1);
    assert.equal(harness.state.feedback?.tone, "error");
    assert.equal(harness.state.feedback?.message, "角色创建失败：角色名称和系统提示词不能为空。");
  });

  it("creates optimistically, refreshes roles, and opens the created role", async () => {
    const createdRole = createRole({ id: "new-role", name: "Mira" });
    const harness = createHarness({
      invoke: async (request) => {
        assert.deepEqual(request, {
          method: "roles.create",
          payload: { name: "Mira", description: "A role", system_prompt: "Be helpful" },
        });
        return createResponse({ role: createdRole });
      },
      loadedRoles: [createdRole],
    });

    const created = await runRoleCreation(createForm(), harness.args);

    assert.equal(created, true);
    assert.equal(harness.state.creating, false);
    assert.equal(harness.state.activeRoleId, "new-role");
    assert.equal(harness.state.activeRoleIdRef.current, "new-role");
    assert.deepEqual(harness.state.roles.map((role) => role.id), ["new-role", "existing"]);
    assert.deepEqual(harness.state.openedRoles, ["new-role"]);
    assert.equal(harness.state.snapshots[0]?.id, "pending-create:test");
    assert.equal(harness.state.snapshots.at(-1)?.id, "new-role");
    assert.equal(harness.state.pendingAction, null);
    // A milestone: 吟风 gets a line for it (see feedbackPersonaLines).
    assert.deepEqual(harness.state.feedback, { tone: "success", message: "角色已创建", options: { persona: "roleCreated" } });
    // The optimistic card shows on the list, then manual creation lands on the new role's detail like an import.
    assert.deepEqual(harness.state.views, [{ kind: "roles-list" }, { kind: "role-detail", roleId: "new-role" }]);
    assert.deepEqual(harness.state.navigationEntries.at(-1)?.view, { kind: "role-detail", roleId: "new-role" });
    assert.equal(harness.state.navigationEntries.at(-1)?.activeRoleId, "new-role");
  });

  it("creates a manual role from its structured profile", async () => {
    const profile = {
      character: {
        profile: "A meticulous archivist.",
        personality: "Calm and precise.",
        behavior_rules: "Use concise answers and cite the archive.",
      },
    };
    const createdRole = createRole({ id: "manual-role", name: "Mira" });
    const harness = createHarness({
      invoke: async (request) => {
        assert.deepEqual(request, {
          method: "roles.create",
          payload: {
            name: "Mira",
            description: "A role",
            system_prompt: "Use concise answers and cite the archive.",
            profile,
          },
        });
        return createResponse({ role: createdRole });
      },
      loadedRoles: [createdRole],
    });

    const created = await runRoleCreation(
      createForm({ profile, systemPrompt: "legacy prompt" }),
      harness.args,
    );

    assert.equal(created, true);
  });

  it("removes the optimistic card and restores the create route after a bridge failure", async () => {
    const harness = createHarness({
      invoke: async () => createResponse({}, { code: "create_failed", message: "保存失败" }),
    });

    const created = await runRoleCreation(createForm(), harness.args);

    assert.equal(created, false);
    assert.equal(harness.state.creating, false);
    assert.deepEqual(harness.state.roles.map((role) => role.id), ["existing"]);
    assert.equal(harness.state.activeRoleId, "existing");
    assert.equal(harness.state.activeRoleIdRef.current, "existing");
    assert.equal(harness.state.pendingAction, null);
    assert.equal(harness.state.feedback?.tone, "error");
    assert.equal(harness.state.feedback?.message, "角色创建失败：保存失败");
    assert.deepEqual(harness.state.views.map((view) => view.kind), ["roles-list", "role-create"]);
    assert.equal(harness.state.navigationEntries.at(-1)?.view.kind, "role-create");
  });

  it("commits a staged role card and opens its detail page", async () => {
    const importedRole = createRole({ id: "imported-role", name: "Imported" });
    const harness = createHarness({
      invoke: async (request) => {
        assert.deepEqual(request, {
          method: "roles.cardImport.commit",
          payload: {
            import_id: "staged-card",
            emotion_selections: {},
            overrides: { name: "Imported", description: "A role", system_prompt: "Be helpful" },
          },
        });
        return createResponse({ role: importedRole });
      },
    });

    const created = await runRoleCreation(
      createForm({ name: "Imported", importId: "staged-card" }),
      harness.args,
    );

    assert.equal(created, true);
    assert.deepEqual(harness.state.views, [{ kind: "role-detail", roleId: "imported-role" }]);
    assert.deepEqual(harness.state.navigationEntries.at(-1)?.view, { kind: "role-detail", roleId: "imported-role" });
    assert.equal(harness.state.refreshCount, 1);
  });

  it("passes selected emotions and refreshes the imported snapshot without restoring cleared rules", async () => {
    const role = createRole({ id: "imported" });
    const refreshedRole = { ...role, description: "Refreshed", avatar: "avatar.png" };
    const profile = { character: { profile: "A librarian", behavior_rules: "", response_constraints: "Brief" } };
    const harness = createHarness({ invoke: async () => createResponse({ role }), loadedRoles: [refreshedRole] });
    assert.equal(await runRoleCreation(createForm({ importId: "card", profile, systemPrompt: "stale rules", emotionSelections: { neutral: "asset-2" } }), harness.args), true);
    assert.deepEqual(harness.state.requests[0]?.payload, {
      import_id: "card", emotion_selections: { neutral: "asset-2" }, overrides: { name: "Mira", description: "A role", profile },
    });
    assert.equal(harness.state.openedSnapshots[0], refreshedRole);
    assert.equal(harness.state.snapshots.at(-1), refreshedRole);
  });

  it("clears busy and optimistic state after a rejected transport request", async () => {
    const harness = createHarness({ invoke: async () => { throw new Error("Bridge disconnected"); } });
    assert.equal(await runRoleCreation(createForm(), harness.args), false);
    assert.equal(harness.state.creating, false);
    assert.equal(harness.state.pendingAction, null);
    assert.deepEqual(harness.state.roles.map((role) => role.id), ["existing"]);
    assert.equal(harness.state.feedback?.tone, "error");
    assert.match(harness.state.feedback?.message ?? "", /disconnected/);
  });

  it("preserves a committed role when its subsequent refresh fails", async () => {
    const harness = createHarness();
    harness.args.loadRolesFromBridge = async () => { throw new Error("Refresh failed"); };
    assert.equal(await runRoleCreation(createForm(), harness.args), true);
    assert.equal(harness.state.requests.length, 1);
    assert.equal(harness.state.activeRoleId, "mira");
    assert.equal(harness.state.creating, false);
    assert.equal(harness.state.pendingAction, null);
    assert.deepEqual(harness.state.views.at(-1), { kind: "role-detail", roleId: "mira" });
    assert.match(harness.state.feedback?.message ?? "", /角色已创建/);
  });
});

describe("role creation form actions", () => {
  it("resets the draft and reports success", () => {
    let form: NewRoleFormState = createForm();
    const feedback = createFeedbackRecorder();
    resetRoleCreationForm({
      updateNewRoleForm: (next) => { form = next; },
      feedback: feedback.reporter,
      openRoleWorkspace: () => undefined,
    });

    assert.deepEqual(form, {
      name: "",
      description: "",
      systemPrompt: "",
      profile: {
        character: { profile: "", personality: "", behavior_rules: "", response_constraints: "" },
      },
    });
    assert.deepEqual(feedback.messages("success"), ["已重置新建角色表单"]);
  });

  it("cancels only when creation is idle", () => {
    let form: NewRoleFormState = createForm();
    const feedback = createFeedbackRecorder();
    const views: AppMainView[] = [];
    const action = {
      updateNewRoleForm: (next: NewRoleFormState) => { form = next; },
      feedback: feedback.reporter,
      openRoleWorkspace: (view: Extract<AppMainView, { kind: "roles-list" | "role-create" | "role-detail" | "role-assets" }>) => { views.push(view); },
    };

    assert.equal(cancelRoleCreation({ ...action, creating: true }), false);
    assert.equal(views.length, 0);
    assert.equal(cancelRoleCreation({ ...action, creating: false }), true);
    assert.deepEqual(form, {
      name: "",
      description: "",
      systemPrompt: "",
      profile: {
        character: { profile: "", personality: "", behavior_rules: "", response_constraints: "" },
      },
    });
    assert.deepEqual(feedback.entries, []);
    assert.deepEqual(views, [{ kind: "roles-list" }]);
  });
});
