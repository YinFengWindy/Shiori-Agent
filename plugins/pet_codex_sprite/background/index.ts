import { surfaceLifecycleEvent, type PluginBackgroundContribution } from "@yinfengwindy/shiori-sdk";
import { SpritePresentationController } from "./controller";

/** Provider readiness follows subscription installation; desktop_pet owns startup policy. */
export default {
  pluginId: "pet_codex_sprite",
  async setup(ctx) {
    const desktop = await ctx.rpc.dependency("desktop_pet");
    if (!desktop) throw new Error("精灵图需要已启用的桌宠插件");
    const controller = new SpritePresentationController(ctx, (report) => desktop.background.call("provider.report", report));
    ctx.effect("sprite_presentations", () => controller.dispose());
    await ctx.events.on("presentation.command", (command) => { void controller.receive(command).catch((error: unknown) => ctx.reportFailure("presentation", error)); });
    ctx.hostEvents.on(surfaceLifecycleEvent, (payload) => { void controller.unavailable(payload).catch((error: unknown) => ctx.reportFailure("presentation.lifecycle", error)); });
    await ctx.rpc.call("presentation.ready", { ready: true });
    // Do not await desktop restore: it may be waiting for this provider's model-loaded report.
    void desktop.background.call("provider.available", { plugin_id: "pet_codex_sprite" }).catch((error: unknown) => ctx.reportFailure("presentation.available", error));
  },
} satisfies PluginBackgroundContribution;
