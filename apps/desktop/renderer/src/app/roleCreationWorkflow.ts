import type React from "react";
import type { BridgeResponse } from "../../../src/bridge/shared";
import type { AppMainView, NewRoleFormState, PendingRoleCardAction, RoleRecord } from "../shared/types";
import { createEmptyNewRoleForm, createPendingRoleRecord, waitForMinimumRoleCardBusy } from "./appState";
import type { NavigationEntry } from "./appState";
import { buildRoleCreationRequest, createRoleFromDraft } from "../roles/roleCreation";
import { errorMessage, type FeedbackReporter } from "../shared/feedback/feedbackStore";

/** Workspace dependencies used to activate and navigate to a created role. */
export type RoleCreationControllerArgs = {
  activeRoleIdRef: React.MutableRefObject<string>;
  setPendingRoleCardAction: React.Dispatch<React.SetStateAction<PendingRoleCardAction>>;
  feedback: FeedbackReporter;
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

/** Injected effects for the shared manual and imported role creation workflow. */
export type RoleCreationWorkflowArgs = RoleCreationControllerArgs & {
  setCreating: React.Dispatch<React.SetStateAction<boolean>>;
  invoke: (request: { method: string; payload: Record<string, unknown> }) => Promise<BridgeResponse>;
  waitForBusy?: (startedAt: number) => Promise<void>;
  createPendingRoleId?: () => string;
};

type FormActionArgs = Pick<RoleCreationControllerArgs, "feedback" | "openRoleWorkspace"> & {
  updateNewRoleForm: (next: NewRoleFormState) => void;
};

/** Resets the new-role draft and its feedback. */
export function resetRoleCreationForm({ updateNewRoleForm, feedback }: FormActionArgs) {
  updateNewRoleForm(createEmptyNewRoleForm());
  feedback.success("已重置新建角色表单");
}

/** Leaves role creation only when there is no creation request in flight. */
export function cancelRoleCreation({ creating, updateNewRoleForm, openRoleWorkspace }: FormActionArgs & { creating: boolean }) {
  if (creating) return false;
  updateNewRoleForm(createEmptyNewRoleForm());
  openRoleWorkspace({ kind: "roles-list" });
  return true;
}

function activateCreatedRole(role: RoleRecord, pendingId: string | undefined, args: RoleCreationWorkflowArgs) {
  args.activeRoleIdRef.current = role.id;
  args.setActiveRoleId(role.id);
  args.setRoles((current) => [role, ...current.filter((item) => item.id !== role.id && item.id !== pendingId)]);
  args.applyRoleSnapshot(role);
}

async function completeRoleCreation(role: RoleRecord, pendingId: string | undefined, imported: boolean, args: RoleCreationWorkflowArgs) {
  activateCreatedRole(role, pendingId, args);
  const nextRoles = await args.loadRolesFromBridge();
  const resolvedRole = nextRoles?.find((item) => item.id === role.id) ?? role;
  activateCreatedRole(resolvedRole, pendingId, args);
  if (!await args.openRole(role.id, resolvedRole, { recordHistory: false })) {
    throw new Error("无法打开已创建的角色会话");
  }
  // Manual creation and card import land in the same place: the new role's detail.
  const destination: AppMainView = { kind: "role-detail", roleId: role.id };
  args.openRoleWorkspace(destination, { recordHistory: false });
  args.replaceNavigationEntry(args.buildNavigationEntry(destination, role.id));
  args.feedback.success(imported ? "角色卡已导入" : "角色已创建");
}

function startOptimisticCreation(form: NewRoleFormState, pendingId: string, args: RoleCreationWorkflowArgs) {
  const pendingRole = createPendingRoleRecord(pendingId, form);
  args.setPendingRoleCardAction({ roleId: pendingId, action: "create" });
  args.setRoles((current) => [pendingRole, ...current]);
  args.applyRoleSnapshot(pendingRole);
  args.openRoleWorkspace({ kind: "roles-list" }, { recordHistory: false });
  args.replaceNavigationEntry(args.buildNavigationEntry({ kind: "roles-list" }, pendingId));
}

function restoreFailedCreation(pendingId: string, previousRoleId: string, args: RoleCreationWorkflowArgs) {
  args.setRoles((current) => current.filter((item) => item.id !== pendingId));
  args.activeRoleIdRef.current = previousRoleId;
  args.setActiveRoleId(previousRoleId);
  args.openRoleWorkspace({ kind: "role-create" }, { recordHistory: false });
  args.replaceNavigationEntry(args.buildNavigationEntry({ kind: "role-create" }, previousRoleId));
}

/** Creates a role through either bridge entry point, then refreshes and activates it once. */
export async function runRoleCreation(form: NewRoleFormState, args: RoleCreationWorkflowArgs) {
  try {
    buildRoleCreationRequest(form);
  } catch (error) {
    args.feedback.error(`角色创建失败：${errorMessage(error)}`);
    return false;
  }

  const imported = Boolean(form.importId);
  const pendingId = imported ? undefined : (args.createPendingRoleId ?? (() => `pending-create:${Date.now()}`))();
  const previousRoleId = args.activeRoleIdRef.current;
  const startedAt = Date.now();
  let createdRole: RoleRecord | undefined;
  args.setCreating(true);
  try {
    if (pendingId) startOptimisticCreation(form, pendingId, args);
    createdRole = await createRoleFromDraft(form, args.invoke);
    if (pendingId) await (args.waitForBusy ?? waitForMinimumRoleCardBusy)(startedAt);
    await completeRoleCreation(createdRole, pendingId, imported, args);
    return true;
  } catch (error) {
    const message = errorMessage(error);
    if (createdRole?.id) {
      // Persistence has succeeded: keep the role so retrying navigation cannot create it again.
      activateCreatedRole(createdRole, pendingId, args);
      const destination = { kind: "role-detail" as const, roleId: createdRole.id };
      args.openRoleWorkspace(destination, { recordHistory: false });
      args.replaceNavigationEntry(args.buildNavigationEntry(destination, createdRole.id));
      args.feedback.error(`角色已创建，打开失败：${message}`);
      return true;
    }
    if (pendingId) restoreFailedCreation(pendingId, previousRoleId, args);
    args.feedback.error(`${imported ? "角色卡导入" : "角色创建"}失败：${message}`);
    return false;
  } finally {
    args.setCreating(false);
    args.setPendingRoleCardAction(null);
  }
}
