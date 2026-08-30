/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import type React from "react";
import type { BridgeResponse } from "../../../src/bridge/shared";
import type { AppMainView, NewRoleFormState, PendingRoleCardAction, RoleRecord } from "../shared/types";
import type { NavigationEntry } from "./appState";
import {
  cancelRoleCreation,
  resetRoleCreationForm,
  runRoleCreation,
  type RoleCreationWorkflowArgs,
} from "./useRoleCreationController";

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
  let error = "";
  let feedback: { tone: "success" | "error"; message: string } | null = null;
  const activeRoleIdRef = { current: activeRoleId };
  const views: AppMainView[] = [];
  const navigationEntries: NavigationEntry[] = [];
  const snapshots: RoleRecord[] = [];
  const requests: Array<{ method: string; payload: Record<string, unknown> }> = [];
  const openedRoles: string[] = [];

  const apply = <T>(current: T, next: T | ((value: T) => T)): T => (
    typeof next === "function" ? (next as (value: T) => T)(current) : next
  );

  const args: RoleCreationWorkflowArgs = {
      activeRoleIdRef,
      setPendingRoleCardAction: (next: React.SetStateAction<PendingRoleCardAction>) => { pendingAction = apply(pendingAction, next); },
      setWorkspaceFeedback: (next: React.SetStateAction<{ tone: "success" | "error"; message: string } | null>) => { feedback = apply(feedback, next); },
      setError: (next: React.SetStateAction<string>) => { error = apply(error, next); },
      setRoles: (next: React.SetStateAction<RoleRecord[]>) => { roles = apply(roles, next); },
      setActiveRoleId: (next: React.SetStateAction<string>) => { activeRoleId = apply(activeRoleId, next); },
      openRoleWorkspace: (view: Extract<AppMainView, { kind: "roles-list" | "role-create" | "role-detail" | "role-assets" }>) => { views.push(view); },
      buildNavigationEntry: (view: AppMainView, roleId = "") => ({ view, activeRoleId: roleId, settingsSection: "models" as const }),
      replaceNavigationEntry: (entry: NavigationEntry) => { navigationEntries.push(entry); },
      loadRolesFromBridge: async () => loadedRoles,
      openRole: async (roleId: string) => { openedRoles.push(roleId); return true; },
      applyRoleSnapshot: (role: RoleRecord) => { snapshots.push(role); },
      setCreating: (next: React.SetStateAction<boolean>) => { creating = apply(creating, next); },
      invoke: async (request: { method: string; payload: Record<string, unknown> }) => { requests.push(request); return invoke(request); },
      waitForBusy: async () => undefined,
      createPendingRoleId: () => "pending-create:test",
  };

  return {
    args,
    get state() {
      return { roles, activeRoleId, activeRoleIdRef, creating, pendingAction, error, feedback, views, navigationEntries, snapshots, requests, openedRoles };
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
    assert.equal(harness.state.error, "角色名称和系统提示词不能为空。");
    assert.equal(harness.state.feedback?.tone, "error");
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
    assert.equal(harness.state.feedback?.message, "角色创建成功。");
    assert.deepEqual(harness.state.views.map((view) => view.kind), ["roles-list", "roles-list"]);
    assert.equal(harness.state.navigationEntries.at(-1)?.activeRoleId, "new-role");
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
    assert.equal(harness.state.error, "保存失败");
    assert.equal(harness.state.feedback?.message, "角色创建失败：保存失败");
    assert.deepEqual(harness.state.views.map((view) => view.kind), ["roles-list", "role-create"]);
    assert.equal(harness.state.navigationEntries.at(-1)?.view.kind, "role-create");
  });
});

describe("role creation form actions", () => {
  it("resets the draft and reports success", () => {
    let form: NewRoleFormState = createForm();
    let feedback: { tone: "success" | "error"; message: string } | null = null;
    resetRoleCreationForm({
      updateNewRoleForm: (next) => { form = next; },
      setWorkspaceFeedback: (next) => { feedback = typeof next === "function" ? next(feedback) : next; },
      openRoleWorkspace: () => undefined,
    });

    assert.deepEqual(form, { name: "", description: "", systemPrompt: "" });
    assert.deepEqual(feedback, { tone: "success", message: "新建角色表单已重置。" });
  });

  it("cancels only when creation is idle", () => {
    let form: NewRoleFormState = createForm();
    let feedback: { tone: "success" | "error"; message: string } | null = { tone: "error", message: "old" };
    const views: AppMainView[] = [];
    const action = {
      updateNewRoleForm: (next: NewRoleFormState) => { form = next; },
      setWorkspaceFeedback: (next: React.SetStateAction<typeof feedback>) => { feedback = typeof next === "function" ? next(feedback) : next; },
      openRoleWorkspace: (view: Extract<AppMainView, { kind: "roles-list" | "role-create" | "role-detail" | "role-assets" }>) => { views.push(view); },
    };

    assert.equal(cancelRoleCreation({ ...action, creating: true }), false);
    assert.equal(views.length, 0);
    assert.equal(cancelRoleCreation({ ...action, creating: false }), true);
    assert.deepEqual(form, { name: "", description: "", systemPrompt: "" });
    assert.equal(feedback, null);
    assert.deepEqual(views, [{ kind: "roles-list" }]);
  });
});
