import type { BackgroundCtx, TtsResult } from "@yinfengwindy/shiori-sdk";
import { liveCancelEvent, liveReplyOutcomeMethod, liveReplyShowEvent, readLiveCancel, readLiveReply } from "./contract";
import { LiveReplyPresenter, type LiveReplyPresenterDeps } from "./replyPresenter";

/**
 * Wires the live-reply entry into the pet background: the backend's
 * `live.reply.show` / `live.cancel` events in, `live.reply.outcome` out, and
 * a disable effect that retires live output. Returns the presenter so the pet
 * can retire live replies when its visible role changes.
 */
export async function registerLiveReplies(
  ctx: Pick<BackgroundCtx, "events" | "rpc" | "effect" | "reportFailure">,
  deps: Pick<LiveReplyPresenterDeps, "bubbles" | "speech" | "ttsProvider" | "visibleRoleId">,
) {
  const presenter = new LiveReplyPresenter({
    ...deps,
    synthesize: (provider, payload) => ctx.rpc.services.call<TtsResult>(provider, "synthesize", payload),
    report: (outcome) => ctx.rpc.call(liveReplyOutcomeMethod, outcome),
  });
  ctx.effect("desktop_pet_live", () => presenter.dispose());
  // Event handlers have no caller to throw at; failures go to the host's diagnostic log.
  await ctx.events.on(liveReplyShowEvent, (payload) => {
    void Promise.resolve().then(() => presenter.show(readLiveReply(payload))).catch((error) => ctx.reportFailure("live.reply", error));
  });
  await ctx.events.on(liveCancelEvent, (payload) => {
    void Promise.resolve().then(() => presenter.cancel(readLiveCancel(payload).runId)).catch((error) => ctx.reportFailure("live.cancel", error));
  });
  return presenter;
}
