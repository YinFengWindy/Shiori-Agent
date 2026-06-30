import type {
  SettingsBindingsSnapshot,
  SettingsChannelGroup,
  SettingsChannelRoleBinding,
  SettingsFormData,
  SettingsPeerAgent,
  SettingsQQBotGroup,
  SettingsSnapshot,
} from "../../../src/shared";

/** Role data returned by the desktop bridge. */
export type RoleRecord = {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  avatar: string | null;
  avatar_abs: string | null;
  featured_image: string | null;
  featured_image_abs: string | null;
  illustrations: string[];
  illustrations_abs: string[];
  created_at: string;
  updated_at: string;
};

/** Single message in a role-bound session. */
export type SessionMessage = {
  id?: string;
  role: string;
  content: string;
  timestamp?: string;
  reasoning_content?: string | null;
  media?: string[];
  metadata?: Record<string, unknown>;
};

/** Session payload returned by the desktop bridge. */
export type SessionPayload = {
  key: string;
  created_at: string;
  updated_at: string;
  last_consolidated: number;
  metadata: Record<string, unknown>;
  messages: SessionMessage[];
};

/** Bridge event row displayed in diagnostics. */
export type EventLog = {
  method: string;
  payload: Record<string, unknown>;
};

/** Editable role form state used by the role editor. */
export type RoleFormState = {
  name: string;
  description: string;
  systemPrompt: string;
  avatarSource: string;
  illustrationSources: string[];
  removedIllustrations: string[];
};

/** New role composer form state. */
export type NewRoleFormState = {
  name: string;
  description: string;
  systemPrompt: string;
};

/** Search result row shown in the desktop sidebar search dialog. */
export type RoleSearchResult = {
  roleId: string;
  roleName: string;
  roleAvatarAbs: string | null;
  sessionKey: string;
  matchedMessageTimestamp: string | null;
  matchedMessageId: string | null;
  matchedMessageIndex: number | null;
  matchedMessagePreview: string;
  matchedField: "role" | "message";
};

/** Main content mode for the desktop shell. */
export type AppMainView =
  | { kind: "chat" }
  | { kind: "image-studio" }
  | { kind: "roles-list" }
  | { kind: "role-create" }
  | { kind: "role-detail"; roleId: string }
  | { kind: "role-assets"; roleId: string }
  | { kind: "settings" };

export type {
  SettingsBindingsSnapshot,
  SettingsChannelGroup,
  SettingsChannelRoleBinding,
  SettingsFormData,
  SettingsPeerAgent,
  SettingsQQBotGroup,
  SettingsSnapshot,
};
