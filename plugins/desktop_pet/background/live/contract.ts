import type { OutputResult } from "../replyOutput";

/**
 * Wire contract between the pet's Python backend (live engine, #724) and this
 * background. Mirrored by `backend/live_output.py`.
 *
 * - backend → background event `live.reply.show`
 *   `{ source: "live", role_id, reply_id, run_id, text }`
 * - backend → background event `live.cancel` `{ run_id?: string }`; without
 *   `run_id` every live run is cancelled. A cancelled run stays cancelled for
 *   the current pet role: later replies of that run are reported `cancelled`.
 * - background → backend RPC `live.reply.outcome`
 *   `{ reply_id, run_id, bubble: OutputResult, speech: OutputResult }`.
 *
 * Outcome guarantee: every `live.reply.show` that carries a `reply_id` and a
 * `run_id` is answered by exactly one outcome — `failed` for a malformed
 * payload or a role the pet does not show, `cancelled` for a cancelled run,
 * a user stop, a role switch or plugin disable, and `skipped` (speech only)
 * when speech was off at the reply's turn. The only reply without an outcome
 * is one arriving after the pet background was already disposed.
 */
export const liveReplyShowEvent = "live.reply.show";
/** Backend event cancelling live replies, optionally of one run. */
export const liveCancelEvent = "live.cancel";
/** Backend RPC receiving each live reply's bubble and speech results. */
export const liveReplyOutcomeMethod = "live.reply.outcome";

/** One live reply to present: the same text is shown and spoken. */
export type LiveReply = { roleId: string; replyId: string; runId: string; text: string };

/** Identifies the reply an outcome answers. */
export type LiveReplyIds = { reply_id: string; run_id: string };

/** The `live.reply.outcome` payload reported back to the backend. */
export type LiveReplyOutcome = LiveReplyIds & { bubble: OutputResult; speech: OutputResult };

/** Parses `live.reply.show`; a malformed payload is a contract violation and throws. */
export function readLiveReply(payload: Record<string, unknown>): LiveReply {
  if (payload.source !== "live") throw new Error("直播回复来源无效");
  return {
    roleId: requireText(payload, "role_id"),
    replyId: requireText(payload, "reply_id"),
    runId: requireText(payload, "run_id"),
    text: requireText(payload, "text"),
  };
}

/** The ids of a possibly malformed `live.reply.show`, so even a rejected reply gets its outcome. */
export function readLiveReplyIds(payload: Record<string, unknown>): LiveReplyIds | null {
  const { reply_id: replyId, run_id: runId } = payload;
  return typeof replyId === "string" && replyId.trim() && typeof runId === "string" && runId.trim()
    ? { reply_id: replyId.trim(), run_id: runId.trim() }
    : null;
}

/** Parses `live.cancel`; an absent `run_id` means every live run. */
export function readLiveCancel(payload: Record<string, unknown>): { runId?: string } {
  if (payload.run_id === undefined) return {};
  return { runId: requireText(payload, "run_id") };
}

function requireText(payload: Record<string, unknown>, key: string) {
  const value = payload[key];
  if (typeof value !== "string" || !value.trim()) throw new Error(`直播回复缺少 ${key}`);
  return value.trim();
}
