import type React from "react";
import { createRoleFormFromRole, isRoleFormDirty } from "../roles/roleFormState";
import type {
  AppMainView,
  RoleFormState,
  RoleRecord,
  SessionPayload,
} from "../shared/types";

type MutableValue<T> = { current: T };

type UseRolePresentationArgs = {
  activeRoleIdRef: MutableValue<string>;
  mainViewRef: MutableValue<AppMainView>;
  roleFormRef: MutableValue<RoleFormState>;
  setActiveRoleId: React.Dispatch<React.SetStateAction<string>>;
  setActiveIllustration: React.Dispatch<React.SetStateAction<string>>;
  setSelectedAvatarAsset: React.Dispatch<React.SetStateAction<string>>;
  setSelectedChatBackground: React.Dispatch<React.SetStateAction<string>>;
  updateRoleForm: (next: React.SetStateAction<RoleFormState>) => void;
};

/** Selects a valid illustration using session, persisted fallback, then role background priority. */
export function chooseRoleIllustration(
  role: RoleRecord | null,
  session: SessionPayload | null,
  fallbackIllustration: string,
): string {
  if (!role) return "";
  const sessionIllustration = String(session?.metadata.active_illustration ?? "");
  if (role.illustrations_abs.includes(sessionIllustration)) {
    return sessionIllustration;
  }
  if (role.illustrations_abs.includes(fallbackIllustration)) {
    return fallbackIllustration;
  }
  const roleChatBackground = String(role.chat_background_abs ?? "");
  return role.illustrations_abs.includes(roleChatBackground) ? roleChatBackground : "";
}

/** Coordinates the active role's persisted assets with its visible desktop snapshot. */
export function useRolePresentation({
  activeRoleIdRef,
  mainViewRef,
  roleFormRef,
  setActiveRoleId,
  setActiveIllustration,
  setSelectedAvatarAsset,
  setSelectedChatBackground,
  updateRoleForm,
}: UseRolePresentationArgs) {
  function applyRoleSnapshot(role: RoleRecord, sessionOverride: SessionPayload | null = null): void {
    setActiveRoleId(role.id);
    activeRoleIdRef.current = role.id;
    const currentView = mainViewRef.current;
    const sameRoleWorkspace =
      (currentView.kind === "role-detail" || currentView.kind === "role-assets")
      && currentView.roleId === role.id;
    if (!sameRoleWorkspace || !isRoleFormDirty(roleFormRef.current, role)) {
      updateRoleForm(createRoleFormFromRole(role));
    }
    setSelectedAvatarAsset(role.avatar ?? "");
    setSelectedChatBackground(role.chat_background ?? "");
    const savedIllustration = window.localStorage.getItem("miraDesktop.activeIllustration") ?? "";
    setActiveIllustration(chooseRoleIllustration(role, sessionOverride, savedIllustration));
  }

  async function rememberIllustration(roleId: string, illustration: string): Promise<void> {
    await window.miraDesktop.invoke({
      method: "session.updateDisplayState",
      payload: {
        role_id: roleId,
        active_illustration: illustration,
      },
    });
  }

  return {
    chooseIllustration: chooseRoleIllustration,
    applyRoleSnapshot,
    rememberIllustration,
  };
}
