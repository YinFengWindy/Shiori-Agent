import type { RoleRecord } from "../shared/types";

/** What clicking 「设为…」 on the assets page changes. */
export type RoleAssetMode = "avatar" | "chat-background" | "mood-binding";

/**
 * Mode tabs, labeled by what they actually set: the role's avatar, the chat
 * backdrop (`chat_background`, drawn behind the whole conversation), and the
 * mood → illustration bindings the chat shows beside the conversation.
 */
export const roleAssetModes: ReadonlyArray<{ id: RoleAssetMode; label: string }> = [
  { id: "avatar", label: "头像" },
  { id: "chat-background", label: "聊天背景" },
  { id: "mood-binding", label: "心情立绘" },
];

/** One image the preview pane shows, with where it comes from. */
export type RoleAssetPreview = {
  relPath: string;
  absPath: string;
  /** Whether it is in the role's asset library (only those can be deleted from here). */
  inLibrary: boolean;
  /** Whether it is what the current mode has set right now (the avatar / the chat background). */
  isCurrent: boolean;
};

type RoleAssetSource = Pick<RoleRecord, "avatar" | "avatar_abs" | "chat_background" | "chat_background_abs" | "illustrations" | "illustrations_abs">;

function libraryAbsPath(role: RoleAssetSource | null, relPath: string): string {
  if (!role || !relPath) return "";
  const index = role.illustrations.indexOf(relPath);
  return index >= 0 ? (role.illustrations_abs[index] ?? "") : "";
}

/**
 * What the mode currently has set. The avatar picked while creating a role is
 * stored outside the asset library (`avatar-*.png` next to it), so a lookup in
 * the library alone would miss it and report 「未设置头像」; the role's own
 * resolved path covers that case.
 */
export function currentRoleAsset(
  mode: RoleAssetMode,
  role: RoleAssetSource | null,
  selectedAvatarAsset: string,
  selectedChatBackground: string,
): RoleAssetPreview | null {
  if (!role || mode === "mood-binding") return null;
  const relPath = mode === "avatar" ? selectedAvatarAsset : selectedChatBackground;
  if (!relPath) return null;
  const libraryPath = libraryAbsPath(role, relPath);
  const ownPath = mode === "avatar"
    ? (relPath === role.avatar ? role.avatar_abs : null)
    : (relPath === role.chat_background ? role.chat_background_abs : null);
  const absPath = libraryPath || ownPath || "";
  return absPath ? { relPath, absPath, inLibrary: Boolean(libraryPath), isCurrent: true } : null;
}

type ResolveRoleAssetPreviewInput = {
  mode: RoleAssetMode;
  role: RoleAssetSource | null;
  /** The library image the user clicked last; empty for none. */
  focusedPath: string;
  selectedAvatarAsset: string;
  selectedChatBackground: string;
};

/** The image the preview pane shows: the clicked library image, else what the mode has set now. */
export function resolveRoleAssetPreview({
  mode,
  role,
  focusedPath,
  selectedAvatarAsset,
  selectedChatBackground,
}: ResolveRoleAssetPreviewInput): RoleAssetPreview | null {
  const current = currentRoleAsset(mode, role, selectedAvatarAsset, selectedChatBackground);
  const focusedAbsPath = libraryAbsPath(role, focusedPath);
  if (focusedAbsPath) {
    return { relPath: focusedPath, absPath: focusedAbsPath, inLibrary: true, isCurrent: focusedPath === current?.relPath };
  }
  return current;
}
