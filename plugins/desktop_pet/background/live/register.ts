import type { BackgroundCtx } from "@yinfengwindy/shiori-sdk";
import { liveCancelEvent, liveReplyOutcomeMethod, liveReplyShowEvent, readLiveCancel } from "./contract";
import { LiveReplyPresenter, type LiveReplyPresenterDeps } from "./replyPresenter";

/** The pet-side collaborators the live entry is wired to. */
export type LiveReplyWiring = Pick<LiveReplyPresenterDeps, "bubbles" | "speech" | "ttsProvider"> & {
  /** Subscribes to the pet's visible role, including the empty role when it hides. */
  watchTarget(listener: (roleId: string) => void): void;
};

/**
 * Wires the live-reply entry into the pet background: the backend's
 * `live.reply.show` / `live.cancel` events in, `live.reply.outcome` out, the
 * visible role in, and a disable effect that answers and retires live output.
 */
export async function registerLiveReplies(ctx: Pick<BackgroundCtx, "events" | "rpc" | "effect" | "reportFailure">, wiring: LiveReplyWiring) {
  const presenter = new LiveReplyPresenter({
    bubbles: wiring.bubbles,
    speech: wiring.speech,
    ttsProvider: wiring.ttsProvider,
    rpc: ctx.rpc,
    report: (outcome) => ctx.rpc.call(liveReplyOutcomeMethod, outcome),
  });
  // Event and listener callbacks have no caller to throw at; failures go to the host's diagnostic log.
  // Started synchronously, so a role change takes effect before the next event is handled.
  const run = (operation: string, work: () => Promise<void>) => {
    const report = (error: unknown) => ctx.reportFailure(operation, error);
    try { void work().catch(report); } catch (error) { report(error); }
  };
  ctx.effect("desktop_pet_live", () => presenter.dispose());
  wiring.watchTarget((roleId) => run("live.bind", () => presenter.bind(roleId)));
  await ctx.events.on(liveReplyShowEvent, (payload) => run("live.reply", () => presenter.receive(payload)));
  await ctx.events.on(liveCancelEvent, (payload) => run("live.cancel", () => presenter.cancel(readLiveCancel(payload).runId)));
}
