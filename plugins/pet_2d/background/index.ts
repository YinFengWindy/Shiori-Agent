import { surfaceLifecycleEvent, type PluginBackgroundContribution } from "@yinfengwindy/shiori-sdk";
import { PetProviderController } from "@shiori-plugin/desktop_pet/provider";
import { prepareAvatar } from "./presentation";
import { CaptureCoordinator } from "./capture";
import { AnimationCoordinator } from "./animation";
import { AvatarPreferences } from "./preferences";

/** The 2.5D provider owns windows and model loading, while desktop_pet owns speech and sessions. */
export default {
  pluginId: "pet_2d",
  async setup(ctx) {
    const desktop = await ctx.rpc.dependency("desktop_pet");
    if (!desktop) throw new Error("2.5D 形象需要已启用的桌宠插件");
    const preferences = new AvatarPreferences(ctx.store, await ctx.store.read());
    const capture = new CaptureCoordinator(ctx, preferences), animation = new AnimationCoordinator(ctx, preferences);
    const controller = new PetProviderController(ctx, {
      pluginId: "pet_2d", prepare: prepareAvatar, report: (report) => desktop.background.call("provider.report", report),
      visibility: async (load, shown, surfaceId) => { animation.visibility(load, shown, surfaceId); await capture.visibility(load, shown, surfaceId); },
      message: (load, value) => capture.message(load, value),
    });
    ctx.effect("avatar_presentations", async () => { try { animation.dispose(); capture.dispose(); } finally { await controller.dispose(); } });
    await capture.register();
    await animation.register();
    await ctx.events.on("presentation.command", (command) => { void controller.receive(command).catch((error: unknown) => ctx.reportFailure("presentation", error)); });
    ctx.hostEvents.on(surfaceLifecycleEvent, (payload) => { void controller.unavailable(payload).catch((error: unknown) => ctx.reportFailure("presentation.lifecycle", error)); });
    await ctx.rpc.call("presentation.ready", { ready: true });
    void desktop.background.call("provider.available", { plugin_id: "pet_2d" }).catch((error: unknown) => ctx.reportFailure("presentation.available", error));
  },
} satisfies PluginBackgroundContribution;
