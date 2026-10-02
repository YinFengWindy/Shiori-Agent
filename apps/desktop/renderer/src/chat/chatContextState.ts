import { errorFeedback } from "@shiori/sdk/host-internal";

/** The provider's complete normalized input and actual output reservation. */
export type ContextBudget = {
  estimate: { tokens: number; source: "actual" | "anchor_delta" | "local" };
  context_window_tokens: number;
  max_output_tokens: number | null;
  output_reservation_tokens: number;
  safety_margin_tokens: number;
  input_limit_tokens: number;
  trigger_tokens: number;
  target_tokens: number;
  schema_tokens: number;
  trigger_ratio: number;
  target_ratio: number;
};

/** Shared staged controller outcome; transient degradation never commits a cut. */
export type ContextCompactionResult = {
  committed: boolean;
  memory_committed: boolean;
  before_tokens: number | null;
  after_tokens: number | null;
  retained_turns: number;
  failure_stage: string;
  error: string;
  detail?: string;
  model?: string;
  phase?: string;
  reason?: "auto_threshold" | "manual" | "hard_limit" | string;
  before_source?: ChatContextStatus["source"];
  after_source?: ChatContextStatus["source"];
  budget?: ContextBudget | null;
  final_budget?: ContextBudget | null;
  attempts?: number;
  compaction_count?: number;
  configured_retained_turns?: number;
  retained_start?: number;
  snapshot_stop?: number;
  retained_reduction_reason?: string;
  memory_required?: boolean;
  memory_start?: number | null;
  memory_stop?: number | null;
  memory_status?: string;
  memory_cursor?: number;
  memory_version?: number;
  window_start?: number;
  window_version?: number;
  published_version?: number;
  relationship_version?: number;
  degraded?: boolean;
  degradation_attempts?: number;
  removed_categories?: string[];
  tools_disabled?: boolean;
  failure_kind?: string;
  request_owner?: string;
  generation?: number;
  request_usage?: Record<string, unknown>;
};

/** Shared minimal budget contract returned by the host's context controller. */
export type ChatContextStatus = {
  session_key: string;
  context_key: string;
  model: string;
  model_identity: string;
  tokens: number | null;
  source: "actual" | "anchor_delta" | "local" | null;
  context_window_tokens: number | null;
  input_limit_tokens: number | null;
  can_compact: boolean;
  busy: boolean;
  reason: string;
  budget?: ContextBudget;
  configured_retained_turns?: number;
  compaction_count?: number;
  window_start?: number;
  window_version?: number;
  memory_cursor?: number;
  memory_version?: number;
  published_version?: number;
  relationship_version?: number;
  memory_status?: string;
  last_compaction?: Omit<ContextCompactionResult, "error"> | null;
  last_request?: Omit<ContextCompactionResult, "error"> | null;
  result: ContextCompactionResult | null;
};

/** Display only server usage; unknown capacity or usage never becomes zero. */
export function contextUsageLabel(status: ChatContextStatus | null) {
  const tokens = status?.tokens;
  const capacity = status?.context_window_tokens;
  if (tokens == null || capacity == null || capacity <= 0 || !Number.isFinite(tokens) || !Number.isFinite(capacity)) {
    return { label: "上下文用量未知", ratio: null };
  }
  const ratio = tokens / capacity;
  const source = status?.source === "actual" ? "实际" : status?.source === "anchor_delta" ? "锚点估算" : "本地估算";
  return { label: `上下文 ${tokens.toLocaleString()} / ${capacity.toLocaleString()}，${Math.round(ratio * 100)}%（${source}）`, ratio };
}

/** Preserve the controller's distinction between memory and window commits. */
export function contextResultLabel(status: ChatContextStatus) {
  return contextResultFeedback(status).message;
}

/** Use the existing feedback boundary for technical diagnostics and secret redaction. */
export function contextResultFeedback(status: ChatContextStatus) {
  const result = status.result;
  if (!result) return errorFeedback(status.reason, "当前无法压缩上下文");
  if (result.committed) return { message: `上下文已压缩：${result.before_tokens?.toLocaleString() ?? "未知"} → ${result.after_tokens?.toLocaleString() ?? "未知"} token（估算）`, detail: "" };
  const failure = errorFeedback({ message: result.error, details: { detail: result.detail } }, "压缩未完成，请稍后重试");
  return { ...failure, message: `${result.memory_committed ? "记忆已整理、压缩失败" : "压缩失败"}：${failure.message}` };
}
