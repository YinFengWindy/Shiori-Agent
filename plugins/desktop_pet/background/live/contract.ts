/**
 * Wire contract between the pet's Python backend (live engine, #724) and this
 * background. Mirrored by `backend/live_output.py`.
 *
 * - backend → background event `live.reply.show`
 *   `{ source: "live", role_id, reply_id, run_id, text }`
 * - backend → background event `live.cancel` `{ run_id?: string }`; without
 *   `run_id` every live reply is cancelled.
 * - background → backend RPC `live.reply.outcome`, once per shown reply:
 *   `{ reply_id, run_id, bubble: OutputResult, speech: OutputResult }`.
 */
export const liveReplyShowEvent = "live.reply.show";
/** Backend event cancelling live replies, optionally of one run. */
export const liveCancelEvent = "live.cancel";
/** Backend RPC receiving each live reply's bubble and speech results. */
export const liveReplyOutcomeMethod = "live.reply.outcome";

/** One live reply to present: the same text is shown and spoken. */
export type LiveReply = { roleId: string; replyId: string; runId: string; text: string };

/** How one output channel (bubble or speech) ended for one reply. */
export type OutputResult =
  | { status: "succeeded" }
  | { status: "cancelled" }
  | { status: "failed"; error: string };

/** The `live.reply.outcome` payload reported back to the backend. */
export type LiveReplyOutcome = { reply_id: string; run_id: string; bubble: OutputResult; speech: OutputResult };

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
