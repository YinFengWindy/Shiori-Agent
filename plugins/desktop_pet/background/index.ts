import { reportBackgroundFailure } from "../../../apps/desktop/renderer/src/background/backgroundDiagnostics";
import type { BackgroundCtx } from "../../../apps/desktop/renderer/src/background/pluginBackgroundRegistry";
import { readDesktopPetBinding } from "./binding";
import { DesktopPetController, desktopPetSurfaceId } from "./controller";
import { normalizeDesktopPetSettings } from "./settings";

/** Identifies the pet's own item in the host tray menu. */
export const desktopPetTrayEntryId = "toggle";

function reportError(operation: string, error: unknown): void {
  // Routed to the host's diagnostic log rather than to this window's console,
  // which nobody can open: `show` failing is exactly what the user is looking
  // at when they report "点了托盘没反应".
  reportBackgroundFailure(`desktop_pet ${operation}`, error);
}

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
export default {
  pluginId: "desktop_pet",
  async setup(ctx: BackgroundCtx): Promise<void> {
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
};
