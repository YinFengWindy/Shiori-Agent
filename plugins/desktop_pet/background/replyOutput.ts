/** Which producer a reply belongs to; source-scoped cancellation never crosses sources. */
export type PetReplySource = "chat" | "live";

/**
 * Identifies who produced a bubble or a speech job. Compared by reference
 * where ownership matters; `runId` narrows live cancellation to one run.
 */
export type ReplyOwner = { readonly source: PetReplySource; readonly runId?: string };

/**
 * How one output channel ended for one reply: bubble, speech job, or the
 * `live.reply.outcome` report. `skipped` means speech was off when the reply
 * reached its turn, so nothing was synthesized.
 */
export type OutputResult =
  | { status: "succeeded" }
  | { status: "cancelled" }
  | { status: "skipped" }
  | { status: "failed"; error: string };

/** Shared results without per-call allocation. */
export const succeededResult: OutputResult = { status: "succeeded" };
export const cancelledResult: OutputResult = { status: "cancelled" };
export const skippedResult: OutputResult = { status: "skipped" };
/** Builds a failed result carrying a human-readable reason. */
export const failedResult = (error: string): OutputResult => ({ status: "failed", error });

/** The reason a reply cannot be shown: the pet is hidden or shows another role. */
export const roleNotShownError = "桌宠未显示该回复的角色";
