import type { SettingsSectionId } from "../settings/SettingsSidebar";
import type {
  AppMainView,
  NewRoleFormState,
  RoleFormState,
  RoleRecord,
  SessionPayload,
} from "../shared/types";

export const sidebarMinWidth = 220;
export const sidebarMaxWidth = 400;
export const sidebarDefaultWidth = 220;
export const sidebarCollapseThreshold = sidebarMinWidth / 2;
export const historySidebarMinWidth = 126;
export const historySidebarMaxWidth = 280;
export const historySidebarDefaultWidth = 126;
export const chatLatestImageSidebarMinWidth = 180;
export const chatLatestImageSidebarMaxWidth = 360;
export const chatLatestImageSidebarDefaultWidth = 220;
export const sidebarAnimationDurationMs = 480;
export const sidebarAutoCollapseWindowWidth = 980;
export const minRoleCardBusyMs = 600;

export type SearchableSessionRecord = {
  roleId: string;
  roleName: string;
  roleAvatarAbs: string | null;
  session: SessionPayload;
};

export type NavigationEntry = {
  view: AppMainView;
  activeRoleId: string;
  settingsSection: SettingsSectionId;
};

export type WorkspaceFeedback = {
  tone: "success" | "error";
  message: string;
};

export type PendingMessageNavigation = {
  roleId: string;
  messageKey: string;
};

/** Clones a main-view value so history entries stay immutable. */
export function cloneView(view: AppMainView): AppMainView {
  if (view.kind === "role-detail") {
    return { kind: "role-detail", roleId: view.roleId };
  }
  if (view.kind === "role-assets") {
    return { kind: "role-assets", roleId: view.roleId };
  }
  return { kind: view.kind };
}

/** Checks whether two main-view values point at the same surface. */
export function viewsEqual(left: AppMainView, right: AppMainView): boolean {
  if (left.kind !== right.kind) {
    return false;
  }
  if (left.kind === "role-detail" && right.kind === "role-detail") {
    return left.roleId === right.roleId;
  }
  if (left.kind === "role-assets" && right.kind === "role-assets") {
    return left.roleId === right.roleId;
  }
  return true;
}

/** Checks whether two history entries should be treated as the same navigation target. */
export function navigationEntriesEqual(left: NavigationEntry, right: NavigationEntry): boolean {
  return (
    viewsEqual(left.view, right.view)
    && left.activeRoleId === right.activeRoleId
    && left.settingsSection === right.settingsSection
  );
}

/** Creates an empty role-edit form state. */
export function createEmptyRoleForm(): RoleFormState {
  return {
    name: "",
    description: "",
    systemPrompt: "",
    nsfwMemoryEnabled: false,
    avatarSource: "",
    illustrationSources: [],
    removedIllustrations: [],
  };
}

/** Creates an empty new-role form state. */
export function createEmptyNewRoleForm(): NewRoleFormState {
  return {
    name: "",
    description: "",
    systemPrompt: "",
  };
}

/** Builds a temporary optimistic role record while role creation is in flight. */
export function createPendingRoleRecord(
  roleId: string,
  form: NewRoleFormState,
): RoleRecord {
  const timestamp = new Date().toISOString();
  return {
    id: roleId,
    name: form.name.trim() || "新角色",
    description: form.description,
    system_prompt: form.systemPrompt,
    runtime_config: {},
    avatar: null,
    avatar_abs: null,
    chat_background: null,
    chat_background_abs: null,
    illustrations: [],
    illustrations_abs: [],
    created_at: timestamp,
    updated_at: timestamp,
  };
}

/** Resolves the desktop role id for a session payload. */
export function getRoleIdFromSession(session: SessionPayload): string {
  const metadataRoleId = String(session.metadata.role_id ?? "").trim();
  if (metadataRoleId) {
    return metadataRoleId;
  }
  return session.key.startsWith("role:") ? session.key.slice(5) : "";
}

/** Identifies assistant proactive pushes so unread dots only count those messages. */
export function isProactiveAssistantMessage(session: SessionPayload): boolean {
  const lastMessage = session.messages[session.messages.length - 1];
  if (!lastMessage || lastMessage.role !== "assistant") {
    return false;
  }
  return Boolean(lastMessage.metadata?.proactive);
}
