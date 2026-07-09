import type {
  SettingsBindingsSnapshot,
  SettingsChannelGroup,
  SettingsChannelRoleBinding,
  SettingsFormData,
  SettingsSnapshot,
} from "../../../src/shared.js";

/** Role data returned by the desktop bridge. */
export type RelationshipSnapshot = {
  role_id: string;
  role_self_view: string;
  relation_tags: string[];
  internal_profile: {
    relation_state: Record<string, number>;
    behavior_profile: Record<string, number>;
  };
  source_summary: Record<string, unknown>;
  generated_at: string;
  last_attempted_at: string;
  last_error: string;
};

export type LonelinessRuntime = {
  role_id: string;
  loneliness_value: number;
  last_calculated_at: string;
  last_user_at: string;
  last_proactive_at: string;
  awaiting_reply_after_proactive: boolean;
  awaiting_reply_since: string;
  last_triggered_at: string;
  cooldown_until: string;
};

export type RoleRecord = {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  runtime_config: Record<string, unknown>;
  avatar: string | null;
  avatar_abs: string | null;
  chat_background: string | null;
  chat_background_abs: string | null;
  illustrations: string[];
  illustrations_abs: string[];
  relationship_snapshot?: RelationshipSnapshot | null;
  loneliness_runtime?: LonelinessRuntime | null;
  created_at: string;
  updated_at: string;
};

/** Single message in a role-bound session. */
export type SessionMessage = {
  id?: string;
  /** Stable renderer-only identity used to keep one visual message node mounted across local and bridge updates. */
  render_id?: string;
  role: string;
  content: string;
  timestamp?: string;
  reasoning_content?: string | null;
  media?: string[];
  metadata?: Record<string, unknown>;
};

/** Referenced chat message shown above the composer before sending. */
export type ChatReplyTarget = {
  messageId: string;
  content: string;
  sender: string;
  preview: string;
};

/** Chat composer payload submitted from the desktop chat surface. */
export type ChatSendRequest = {
  content: string;
  attachments: string[];
  replyTarget: ChatReplyTarget | null;
};

/** Session payload returned by the desktop bridge. */
export type SessionPayload = {
  key: string;
  created_at: string;
  updated_at: string;
  last_consolidated: number;
  metadata: Record<string, unknown> & {
    relationship_snapshot?: RelationshipSnapshot | null;
    loneliness_runtime?: LonelinessRuntime | null;
  };
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
  nsfwMemoryEnabled: boolean;
  avatarSource: string;
  illustrationSources: string[];
  removedIllustrations: string[];
  moodCatalog: string[];
  defaultMood: string;
  moodIllustrationBindings: Record<string, string>;
};

/** New role composer form state. */
export type NewRoleFormState = {
  name: string;
  description: string;
  systemPrompt: string;
};

/** Pending role card action shown directly in the role list. */
export type PendingRoleCardAction =
  | { roleId: string; action: "create" | "delete" }
  | null;

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
  SettingsSnapshot,
};
