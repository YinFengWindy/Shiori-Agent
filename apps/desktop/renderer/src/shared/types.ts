import type { SessionMessagePage, SessionSummary } from "@shiori/plugin-sdk";
import type {
  SettingsFormData,
  SettingsSnapshot,
} from "../../../src/bridge/shared.js";

/** Session type a channel declares; the desktop session is private. */
export type RoleChatType = "private" | "group";

export type RoleTaskKind = "schedule" | "subagent" | "memory_maintenance";

export type ScheduleTaskTier = "instant" | "soft";

export type ScheduleTaskTrigger = "at" | "after" | "every";

/** Editable fields accepted by the desktop scheduled-task API. */
export type ScheduleTaskFormData = {
  name: string;
  tier: ScheduleTaskTier;
  trigger: ScheduleTaskTrigger;
  when: string;
  content: string;
};

/** Scheduler fields exposed for one editable role task. */
export type RoleTaskSchedule = Omit<ScheduleTaskFormData, "name">;

/** Role-owned background work returned by the desktop bridge. */
export type RoleTask = {
  id: string;
  role_id: string;
  kind: RoleTaskKind;
  status: string;
  label: string;
  detail: string;
  created_at: string;
  next_run_at: string;
  cancellable: boolean;
  editable: boolean;
  schedule: RoleTaskSchedule | null;
};

export type ChatTurnMetrics = {
  total_tokens?: number;
  thinking_duration_ms?: number;
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

/** Paginated session payload returned when a role session is opened. */
export type SessionOpenPayload = {
  session: SessionSummary;
  page: SessionMessagePage;
};

/** Lightweight persisted-message hit returned by the desktop search API. */
export type SessionSearchResult = {
  id: string;
  session_key: string;
  seq: number;
  role: string;
  preview: string;
  timestamp: string | null;
};

/** Lightweight persisted media projection used outside the paginated chat window. */
export type SessionImageHistoryMessage = {
  id: string;
  seq: number;
  timestamp: string | null;
  media: unknown[];
};

/** Editable role form state used by the role editor. */
export type ManagedVoiceAssetReference = {
  provider: string;
  voiceId: string;
  ownership: "shiori_managed";
};

export type RoleFormState = {
  name: string;
  description: string;
  systemPrompt: string;
  profile?: RoleProfileDraft;
  nsfwMemoryEnabled: boolean;
  /** Draft values owned by registered role-setting plugins. */
  pluginSettings: import("../plugins/pluginRoleSettings").PluginRoleSettingsDraft;
  proactiveEnabled?: boolean;
  proactiveProfile?: string;
  proactiveAgentMaxSteps?: number;
  proactiveAgentContentLimit?: number;
  proactiveAgentWebFetchMaxChars?: number;
  proactiveDriftEnabled?: boolean;
  proactiveDriftMaxSteps?: number;
  proactiveDriftMinIntervalHours?: number;
  avatarSource: string;
  illustrationSources: string[];
  removedIllustrations: string[];
  moodCatalog: string[];
  defaultMood: string;
  moodIllustrationBindings: Record<string, string>;
  voiceEnabled: boolean;
  voiceProvider: string;
  voiceOwnership: "external" | "shiori_managed";
  voiceId: string;
  voiceName: string;
  voiceSpeed: number;
  voiceMoodEmotions: Record<string, string>;
  pendingVoiceAssetDeletes: ManagedVoiceAssetReference[];
};

/** New role composer form state. */
export type NewRoleFormState = {
  name: string;
  description: string;
  systemPrompt: string;
  /** Selected local image; an empty string explicitly removes an imported avatar. */
  avatarSource?: string;
  profile?: RoleProfileDraft;
  /** Server-owned staging import id; never a renderer filesystem path. */
  importId?: string;
  /** Explicit choices for duplicate emotion assets, keyed by mood name. */
  emotionSelections?: Record<string, string>;
};

/** Non-runtime metadata retained from an imported character card. */
export type RoleImportProvenance = {
  format: string;
  card_version?: string | null;
  creator?: string;
  tags?: string[];
  source?: string[];
  created_at?: string | number | null;
  updated_at?: string | number | null;
  imported_at?: string;
};

/** Editable structured role data shared by card import and role persistence. */
export type RoleProfileDraft = {
  character?: { profile?: string; personality?: string; behavior_rules?: string; response_constraints?: string; nickname?: string };
  import_provenance?: RoleImportProvenance;
};

/** A decoded candidate image in a staged import. */
export type RoleCardImportAsset = {
  asset_id: string;
  kind?: string;
  name?: string | null;
  path?: string;
  media_type?: string | null;
  size?: number;
  preview_abs?: string;
};

/** Structured preview returned by the role-card import bridge. */
export type RoleCardImportPreview = {
  import_id: string;
  system_prompt?: string;
  name?: string;
  description?: string;
  profile?: RoleProfileDraft;
  report?: {
    adapted_fields?: string[];
    discarded_fields?: string[];
    unsupported_macros?: string[];
    unsupported_resources?: string[];
    unsupported_rules?: string[];
  };
  assets?: RoleCardImportAsset[];
  provenance?: RoleImportProvenance | null;
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
  | { kind: "roles-list" }
  | { kind: "role-create" }
  | { kind: "role-detail"; roleId: string }
  | { kind: "role-assets"; roleId: string }
  | { kind: "settings" }
  | { kind: "plugin-page"; pageId: string };

export type {
  SettingsFormData,
  SettingsSnapshot,
};
