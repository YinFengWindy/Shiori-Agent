import { useState } from "react";
import type React from "react";
import { createEmptyNewRoleForm, createPendingRoleRecord, waitForMinimumRoleCardBusy } from "./appState";
import type { AppMainView, NewRoleFormState, PendingRoleCardAction, RoleRecord } from "../shared/types";
import type { NavigationEntry } from "./appState";
import { useLatestRef } from "../shared/useLatestRef";
import type { BridgeResponse } from "../../../src/bridge/shared";

/** Dependencies shared by the React controller and its role-creation workflow. */
export type RoleCreationControllerArgs = {
  activeRoleIdRef: React.MutableRefObject<string>;
  setPendingRoleCardAction: React.Dispatch<React.SetStateAction<PendingRoleCardAction>>;
  setWorkspaceFeedback: React.Dispatch<React.SetStateAction<{ tone: "success" | "error"; message: string } | null>>;
  setError: React.Dispatch<React.SetStateAction<string>>;
  setRoles: React.Dispatch<React.SetStateAction<RoleRecord[]>>;
  setActiveRoleId: React.Dispatch<React.SetStateAction<string>>;
  openRoleWorkspace: (
    nextView: Extract<AppMainView, { kind: "roles-list" | "role-create" | "role-detail" | "role-assets" }>,
    options?: { recordHistory?: boolean },
  ) => void;
  buildNavigationEntry: (view: AppMainView, roleId?: string) => NavigationEntry;
  replaceNavigationEntry: (entry: NavigationEntry) => void;
  loadRolesFromBridge: () => Promise<RoleRecord[] | null>;
  openRole: (roleId: string, roleOverride?: RoleRecord | null, options?: { recordHistory?: boolean }) => Promise<boolean>;
  applyRoleSnapshot: (role: RoleRecord) => void;
};

/** Dependencies required to execute the role-creation workflow. */
export type RoleCreationWorkflowArgs = RoleCreationControllerArgs & {
  setCreating: React.Dispatch<React.SetStateAction<boolean>>;
  invoke: (request: { method: string; payload: Record<string, unknown> }) => Promise<BridgeResponse>;
  waitForBusy?: (startedAt: number) => Promise<void>;
  createPendingRoleId?: () => string;
};

type RoleCreationFormActionArgs = {
  updateNewRoleForm: (next: NewRoleFormState) => void;
  setWorkspaceFeedback: React.Dispatch<React.SetStateAction<{ tone: "success" | "error"; message: string } | null>>;
  openRoleWorkspace: RoleCreationControllerArgs["openRoleWorkspace"];
};

/** Resets the new-role draft and reports the action to the workspace shell. */
export function resetRoleCreationForm({ updateNewRoleForm, setWorkspaceFeedback }: RoleCreationFormActionArgs): void {
  updateNewRoleForm(createEmptyNewRoleForm());
  setWorkspaceFeedback({ tone: "success", message: "新建角色表单已重置。" });
}

/** Cancels role creation when no create request is in flight. */
export function cancelRoleCreation({
  creating,
  updateNewRoleForm,
  setWorkspaceFeedback,
  openRoleWorkspace,
}: RoleCreationFormActionArgs & { creating: boolean }): boolean {
  if (creating) {
    return false;
  }
  updateNewRoleForm(createEmptyNewRoleForm());
  setWorkspaceFeedback(null);
  openRoleWorkspace({ kind: "roles-list" });
  return true;
}

/** Runs the role-create side effects independently of React so the contract remains directly testable. */
export async function runRoleCreation(
  form: NewRoleFormState,
  {
    activeRoleIdRef,
    setPendingRoleCardAction,
    setWorkspaceFeedback,
    setError,
    setRoles,
    setActiveRoleId,
    openRoleWorkspace,
    buildNavigationEntry,
    replaceNavigationEntry,
    loadRolesFromBridge,
    openRole,
    applyRoleSnapshot,
    setCreating,
    invoke,
    waitForBusy = waitForMinimumRoleCardBusy,
    createPendingRoleId = () => `pending-create:${Date.now()}`,
  }: RoleCreationWorkflowArgs,
): Promise<boolean> {
  const name = form.name.trim();
  const systemPrompt = form.systemPrompt.trim();
  if (!name || !systemPrompt) {
    const message = "角色名称和系统提示词不能为空。";
    setError(message);
    setWorkspaceFeedback({ tone: "error", message: `角色创建失败：${message}` });
    return false;
  }

  const pendingRoleId = createPendingRoleId();
  const pendingRole = createPendingRoleRecord(pendingRoleId, form);
  const previousActiveRoleId = activeRoleIdRef.current;
  const startedAt = Date.now();
  setCreating(true);
  setError("");
  setWorkspaceFeedback(null);
  setPendingRoleCardAction({ roleId: pendingRoleId, action: "create" });
  setRoles((current) => [pendingRole, ...current]);
  applyRoleSnapshot(pendingRole);
  openRoleWorkspace({ kind: "roles-list" }, { recordHistory: false });
  replaceNavigationEntry(buildNavigationEntry({ kind: "roles-list" }, pendingRoleId));

  const res = await invoke({
    method: "roles.create",
    payload: { name, description: form.description, system_prompt: systemPrompt },
  });
  await waitForBusy(startedAt);
  setCreating(false);
  if (res.error) {
    setPendingRoleCardAction(null);
    setRoles((current) => current.filter((item) => item.id !== pendingRoleId));
    setActiveRoleId(previousActiveRoleId);
    activeRoleIdRef.current = previousActiveRoleId;
    openRoleWorkspace({ kind: "role-create" }, { recordHistory: false });
    replaceNavigationEntry(buildNavigationEntry({ kind: "role-create" }, previousActiveRoleId));
    setError(res.error.message);
    setWorkspaceFeedback({ tone: "error", message: `角色创建失败：${res.error.message}` });
    return false;
  }

  const role = res.payload.role as RoleRecord;
  activeRoleIdRef.current = role.id;
  setActiveRoleId(role.id);
  setPendingRoleCardAction({ roleId: role.id, action: "create" });
  setRoles((current) => {
    const withoutPending = current.filter((item) => item.id !== pendingRoleId);
    return [role, ...withoutPending.filter((item) => item.id !== role.id)];
  });
  applyRoleSnapshot(role);
  const nextRoles = await loadRolesFromBridge();
  const resolvedRole = nextRoles?.find((item) => item.id === role.id) ?? role;
  if (!nextRoles?.some((item) => item.id === role.id)) {
    setRoles((current) => [resolvedRole, ...current.filter((item) => item.id !== role.id)]);
  }
  await openRole(role.id, resolvedRole, { recordHistory: false });
  openRoleWorkspace({ kind: "roles-list" }, { recordHistory: false });
  replaceNavigationEntry(buildNavigationEntry({ kind: "roles-list" }, resolvedRole.id));
  setPendingRoleCardAction(null);
  setWorkspaceFeedback({ tone: "success", message: "角色创建成功。" });
  return true;
}

/** Owns new-role form state and the full create/cancel/recovery workflow. */
export function useRoleCreationController({
  activeRoleIdRef,
  setPendingRoleCardAction,
  setWorkspaceFeedback,
  setError,
  setRoles,
  setActiveRoleId,
  openRoleWorkspace,
  buildNavigationEntry,
  replaceNavigationEntry,
  loadRolesFromBridge,
  openRole,
  applyRoleSnapshot,
}: RoleCreationControllerArgs) {
  const [newRoleForm, setNewRoleForm] = useState(createEmptyNewRoleForm);
  const [creating, setCreating] = useState(false);
  const newRoleFormRef = useLatestRef(newRoleForm);

  function updateNewRoleForm(next: React.SetStateAction<NewRoleFormState>): void {
    setNewRoleForm((current) => {
      const resolved = typeof next === "function" ? next(current) : next;
      newRoleFormRef.current = resolved;
      return resolved;
    });
  }

  function resetNewRoleForm(): void {
    resetRoleCreationForm({ updateNewRoleForm, setWorkspaceFeedback, openRoleWorkspace });
  }

  async function createRole(): Promise<void> {
    const created = await runRoleCreation(newRoleFormRef.current, {
      activeRoleIdRef,
      setPendingRoleCardAction,
      setWorkspaceFeedback,
      setError,
      setRoles,
      setActiveRoleId,
      openRoleWorkspace,
      buildNavigationEntry,
      replaceNavigationEntry,
      loadRolesFromBridge,
      openRole,
      applyRoleSnapshot,
      setCreating,
      invoke: window.miraDesktop.invoke,
    });
    if (created) {
      updateNewRoleForm(createEmptyNewRoleForm());
    }
  }

  function cancelCreateRole(): void {
    cancelRoleCreation({
      creating,
      updateNewRoleForm,
      setWorkspaceFeedback,
      openRoleWorkspace,
    });
  }

  return { creating, newRoleForm, updateNewRoleForm, resetNewRoleForm, cancelCreateRole, createRole };
}
