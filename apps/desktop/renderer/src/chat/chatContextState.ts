import { errorFeedback } from "@shiori/sdk/host-internal";

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
  result: {
    committed: boolean;
    memory_committed: boolean;
    before_tokens: number;
    after_tokens: number | null;
    retained_turns: number;
    failure_stage: string;
    error: string;
    detail?: string;
  } | null;
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
  if (result.committed) return { message: `上下文已压缩：${result.before_tokens.toLocaleString()} → ${result.after_tokens?.toLocaleString()} token（估算）`, detail: "" };
  const failure = errorFeedback({ message: result.error, details: { detail: result.detail } }, "压缩未完成，请稍后重试");
  return { ...failure, message: `${result.memory_committed ? "记忆已整理、压缩失败" : "压缩失败"}：${failure.message}` };
}
