/** Role records as the desktop bridge returns them (`roles.list`, `host.listRoles()`). */

/** The fixed affection stages, from lowest to highest. */
export type AffectionStageName = "厌恶" | "冷淡" | "陌生" | "熟悉" | "朋友" | "亲密" | "挚爱";

/**
 * A role's affection (-100–100) with its stage and progress within that stage
 * (0–1). The affection plugin serves it through its own RPC; role and session
 * payloads do not carry it.
 */
export type AffectionSummary = {
  value: number;
  stage: AffectionStageName;
  progress: number;
  /**
   * The stage floor the value can no longer drop below (the start of the
   * highest stage reached from 「熟悉」 up); null while there is none.
   * Runtime API 3.1.1.
   */
  floor: number | null;
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
