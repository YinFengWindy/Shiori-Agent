import { BridgeError, errorMessage } from "@shiori/sdk";

// These codes are owned by Story (backend/errors.py and input validation).
// Their messages are actionable domain instructions; transport/internal errors
// use the operation's summary and keep diagnostics in the separate detail.
const domainCodes = new Set(["story_not_found", "revision_conflict", "invalid_state", "turn_busy", "director_invalid_output", "provider_not_configured", "role_required", "invalid_request"]);

/** Separates Story's operation summary from scrubbed RPC or native diagnostics. */
export function describeStoryFailure(cause: unknown, summary = "剧情操作未完成，请重试") {
  const message = errorMessage(cause);
  const error = cause instanceof BridgeError && domainCodes.has(cause.code) ? message : summary;
  const detail = errorMessage(cause, { includeDetail: true });
  return { error, errorDetail: detail && detail !== error ? detail : undefined };
}
