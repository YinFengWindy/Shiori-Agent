import type { PluginBackgroundContribution } from "@yinfengwindy/shiori-sdk";
import { readDesktopPetBinding } from "./binding";
import { DesktopPetController, desktopPetSurfaceId } from "./controller";
import { normalizeDesktopPetSettings } from "./settings";
import { registerLiveReplies } from "./live/register";
import type { LiveReplyPresenter } from "./live/replyPresenter";
import { PetVoiceController } from "./voice/controller";
import { PetSpeechQueue } from "./voice/speechQueue";
import { defaultVoicePreferences, type VoicePreferences } from "./voice/preferences";

/** Identifies the pet's own item in the host tray menu. */
export const desktopPetTrayEntryId = "toggle";

/**
 * The desktop pet's `app.background` contribution: its always-resident
 * controller.
 *
 * Runs in the dedicated hidden `plugin-host.html` renderer, started when the
 * plugin is enabled and torn down when it is disabled — which is what makes
 * #181's "停用桌宠插件后 surface、订阅全部回收" true rather than aspirational.
 * The `ctx.effect` below is what reclaims the window; the subscriptions are
 * reclaimed by `BackgroundEffectScope` regardless of the order they were
 * registered in (#227), so the `effect`/`on` ordering here is a readability
 * choice, not a correctness one.
 */
const desktopPetBackground = {
  pluginId: "desktop_pet",
  async setup(ctx) {
    // Routed to the host's diagnostic log rather than to this window's console,
    // which nobody can open: `show` failing is exactly what the user is looking
    // at when they report "点了托盘没反应".
    const reportError = (operation: string, error: unknown) => ctx.reportFailure(operation, error);
    let voice: PetVoiceController | null = null;
    let live: LiveReplyPresenter | null = null;

    const controller = new DesktopPetController({
      surfaces: ctx.surfaces,
      settings: normalizeDesktopPetSettings(await ctx.store.read()),
      saveSettings: (settings) => ctx.store.write(settings),
      resolveBinding: async () => readDesktopPetBinding(
        await ctx.rpc.call("binding.get"),
        (path) => ctx.assets.url(path),
      ),
      onError: reportError,
      onChanged: () => refreshTrayEntry(),
      onTargetChanged: (roleId) => {
        voice?.bind(roleId);
        void live?.bind(roleId).catch((error) => reportError("live.cancel", error));
      },
    });

    /**
     * Keeps the tray item in step with the pet.
     *
     * The label and the enabled state are both pet domain facts — is it
     * showing, and is there a role with a package to show — which is exactly
     * why this moved out of the host in #181-D. The host used to read them out
     * of the pet's settings blob and build the item itself.
     */
    const refreshTrayEntry = () => {
      const settings = controller.currentSettings;
      const available = Boolean(settings.roleId && settings.packageId);
      ctx.tray.setEntry(desktopPetTrayEntryId, {
        label: settings.visible ? "隐藏桌宠" : "显示桌宠",
        enabled: available,
        onClick: () => {
          const operation = settings.visible ? "hide" : "show";
          void (settings.visible ? controller.hide() : controller.show())
            .catch((error) => reportError(operation, error));
        },
      });
    };
    // Contributed once up front, so the item exists from the moment the plugin
    // is enabled rather than only after the pet's first state change.
    refreshTrayEntry();
    // Optional speech initialization cannot tear down the pet's visual and text features.
    // One speech line for every reply source, so chat and live speech never overlap.
    const speech = new PetSpeechQueue(ctx.native.audio);
    try {
      const preferences = await ctx.rpc.call<VoicePreferences>("voice.preferences.get");
      voice = new PetVoiceController(ctx, preferences, (state) => controller.publishVoice(state), speech);
    } catch (error) {
      reportError("voice.preferences", error);
      voice = new PetVoiceController(ctx, defaultVoicePreferences, (state) => controller.publishVoice(state), speech);
    }
    const activeVoice = voice;
    ctx.effect("desktop_pet_voice", () => activeVoice.dispose());
    live = await registerLiveReplies(ctx, {
      bubbles: controller.replies,
      speech,
      ttsProvider: () => activeVoice.ttsProvider,
      visibleRoleId: () => controller.visibleRoleId,
    });
    ctx.surfaces.onMessage(desktopPetSurfaceId, (message) => {
      if (!message || typeof message !== "object" || !("kind" in message)) return;
      if (message.kind === "voice.stop") activeVoice.stop();
      if (message.kind === "voice.gesture" && "gesture" in message) activeVoice.gesture(String(message.gesture));
    });
    await ctx.events.on("voice.preferences.changed", (payload) => { void activeVoice.configure(payload as VoicePreferences).catch((error) => reportError("voice.preferences", error)); });
    await ctx.rpc.handle("voice.devices", () => ctx.native.audio.devices());
    await ctx.rpc.handle("voice.preferences.validate", (payload) => ctx.native.keys.validate(String(payload.hotkey ?? "")));
    await ctx.rpc.handle("voice.stop", () => activeVoice.stop());
    for (const method of ["chat.delta", "chat.done", "chat.error"]) ctx.hostEvents.on(method, (_payload, event) => activeVoice.handle(event));

    ctx.effect("desktop_pet_controller", () => controller.terminate());
    ctx.surfaces.onSettled(desktopPetSurfaceId, (settled) => controller.handleSettled(settled));
    await ctx.events.on("action", (payload) => controller.handleAgentAction(payload));
    await ctx.rpc.handle("sync", async (payload) => {
      const forceVisible = typeof payload.forceVisible === "boolean" ? payload.forceVisible : undefined;
      await controller.sync(forceVisible);
    });
    for (const method of ["chat.done", "session.updated"]) {
      ctx.hostEvents.on(method, (_payload, event) => controller.replies.handleEvent(event));
    }
    ctx.hostEvents.on("system.lock-state", (payload) => {
      if (typeof payload.locked === "boolean") controller.replies.setLocked(payload.locked);
      if (typeof payload.locked === "boolean") activeVoice.setLocked(payload.locked);
    });
    await ctx.events.on("bubble.dismissed", () => controller.replies.dismiss());

    // Reported rather than rethrown: a failed restore (the bridge answering
    // late, say) must not fail `setup`, because a thrown `setup` tears the
    // whole contribution down and nothing retries it — the pet would then stay
    // dead until the app restarted. Letting it fail leaves the pet hidden,
    // which the tray entry can undo.
    try {
      await controller.restore();
    } catch (error) {
      reportError("restore", error);
    }
  },
} satisfies PluginBackgroundContribution;

export default desktopPetBackground;
