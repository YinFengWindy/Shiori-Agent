/** Role records as the desktop bridge returns them (`roles.list`, `host.listRoles()`). */

/**
 * The relationship dimensions of a snapshot, each 0–1. Closeness was removed in
 * Runtime API 3.1.9; the role's affection (`AffectionSummary`) replaces it.
 */
export type RelationState = {
  dependence: number;
  security: number;
  initiative_desire: number;
  neglect_sensitivity: number;
};

/** A role's generated relationship snapshot (its self view and relation tags). */
export type RelationshipSnapshot = {
  role_id: string;
  role_self_view: string;
  relation_tags: string[];
  internal_profile: {
    relation_state: RelationState;
    behavior_profile: Record<string, number>;
  };
  source_summary: Record<string, unknown>;
  generated_at: string;
  last_attempted_at: string;
  last_error: string;
};

/** A role's loneliness state that drives proactive messages. */
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

/** The fixed affection stages, from lowest to highest. */
export type AffectionStageName = "厌恶" | "冷淡" | "陌生" | "熟悉" | "朋友" | "亲密" | "挚爱";

/** A role's affection (-100–100) with its stage and progress within that stage (0–1). */
export type AffectionSummary = {
  value: number;
  stage: AffectionStageName;
  progress: number;
};

/** Role data returned by the desktop bridge. */
export type RoleRecord = {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  profile?: {
    character?: { profile?: string; personality?: string; behavior_rules?: string };
  };
  runtime_config: Record<string, unknown>;
  proactive?: RoleProactiveConfig;
  avatar: string | null;
  avatar_abs: string | null;
  chat_background: string | null;
  chat_background_abs: string | null;
  illustrations: string[];
  illustrations_abs: string[];
  asset_categories: RoleAssetCategory[];
  asset_category_bindings: Record<string, string>;
  /** Active plugins project their independently owned role settings here. */
  plugin_state?: Record<string, Record<string, unknown>>;
  relationship_snapshot?: RelationshipSnapshot | null;
  loneliness_runtime?: LonelinessRuntime | null;
  /** Absent until the role's first conversation initializes affection. */
  affection?: AffectionSummary | null;
  /** Newest message of the role's session, for the chat-list preview; null when the session is empty. */
  last_message?: RoleLastMessage | null;
  created_at: string;
  updated_at: string;
};

/** Light preview of a role session's newest message (content capped at 200 chars by the bridge). */
export type RoleLastMessage = {
  role: string;
  content: string;
  timestamp: string;
  has_media: boolean;
};

/** User-defined single-owner category for one role's asset library. */
export type RoleAssetCategory = {
  id: string;
  name: string;
  allow_role_send: boolean;
};

/** A session that may receive proactive messages, by channel and chat id. */
export type RoleProactiveCandidate = {
  channel: string;
  chat_id: string;
};

/** A role's proactive messaging settings. */
export type RoleProactiveConfig = {
  enabled: boolean;
  /** Candidate sessions in binding order; each message goes to the one the backend selects. */
  candidates: RoleProactiveCandidate[];
  profile?: string;
  overrides?: Record<string, Record<string, number>>;
  agent?: {
    max_steps?: number;
    content_limit?: number;
    web_fetch_max_chars?: number;
  };
  drift?: {
    /** Legacy persisted field; idle activity now follows the main enabled switch. */
    enabled?: boolean;
    max_steps?: number;
    min_interval_hours?: number;
  };
};
