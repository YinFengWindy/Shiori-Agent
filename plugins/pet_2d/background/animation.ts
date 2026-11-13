import type { BackgroundCtx } from "@yinfengwindy/shiori-sdk";
import { readPetModelReference, type PetModel } from "@shiori-plugin/desktop_pet/provider";
import { readAnimationSettings, type AnimationCatalog, type AnimationSettings } from "../shared/animation";
import type { AvatarPresentation } from "./presentation";
import type { AvatarPreferences } from "./preferences";

/** Routes preview and persisted settings to every shown copy of the same package. */
export class AnimationCoordinator {
  private readonly shown = new Map<string, { load: AvatarPresentation; surfaceId: string }>();
  private readonly known = new Map<string, Set<string>>();
  private readonly previews = new Map<string, AnimationSettings>();
  private disposed = false;
  constructor(private readonly ctx: Pick<BackgroundCtx, "surfaces" | "rpc">, private readonly preferences: AvatarPreferences) {}
  /** Role-scoped discovery admits the packages the settings dialog can edit. */
  async register() {
    await this.ctx.rpc.handle("animation.models", async (payload): Promise<AnimationCatalog> => {
      if (typeof payload.roleId !== "string" || !payload.roleId) throw new Error("请先保存角色");
      const { models } = await this.ctx.rpc.services.call<{ models: PetModel[] }>({ plugin_id: "pet_2d", service_id: "models" }, "list", { role_id: payload.roleId });
      const desktop = await this.ctx.rpc.dependency("desktop_pet");
      if (!desktop) throw new Error("桌宠插件不可用");
      const selection = await desktop.call<{ selected_model: unknown }>("pets.list", { role_id: payload.roleId });
      const selected = readPetModelReference(selection.selected_model);
      this.known.set(payload.roleId, new Set(models.map((model) => model.id)));
      return { models: models.map((model) => ({ modelId: model.id, name: model.display_name })), selectedModelId: selected?.provider.plugin_id === "pet_2d" ? selected.model_id : null };
    });
    await this.ctx.rpc.handle("animation.get", (payload) => this.preferences.animation(this.modelId(payload)));
    await this.ctx.rpc.handle("animation.preview", (payload) => {
      const id = this.modelId(payload), settings = readAnimationSettings(payload.settings);
      this.previews.set(id, settings); this.broadcast(id, settings);
      return { ok: true };
    });
    await this.ctx.rpc.handle("animation.save", async (payload) => {
      const id = this.modelId(payload), settings = readAnimationSettings(payload.settings);
      await this.preferences.saveAnimation(id, settings);
      // A newer preview may already be on screen while this disk write completes.
      if (!this.disposed && !this.previews.has(id)) this.broadcast(id, settings);
      return settings;
    });
  }
  /** Replays current settings only after the renderer is ready and shown. */
  visibility(load: AvatarPresentation, shown: boolean, surfaceId: string) {
    if (!shown) { this.shown.delete(load.lease_id); return; }
    if (this.disposed) return;
    this.shown.set(load.lease_id, { load, surfaceId });
    this.send(load, surfaceId, this.previews.get(load.model_id) ?? this.preferences.animation(load.model_id));
  }
  /** Stops fan-out when the provider generation retires. */
  dispose() { this.disposed = true; this.shown.clear(); this.previews.clear(); this.known.clear(); }
  private modelId(payload: Record<string, unknown>) {
    if (this.disposed || typeof payload.roleId !== "string" || typeof payload.modelId !== "string" || !this.known.get(payload.roleId)?.has(payload.modelId)) throw new Error("该角色没有这个 2.5D 形象");
    return payload.modelId;
  }
  private broadcast(modelId: string, settings: AnimationSettings) {
    for (const { load, surfaceId } of this.shown.values()) if (load.model_id === modelId) this.send(load, surfaceId, settings);
  }
  private send(load: AvatarPresentation, surfaceId: string, settings: AnimationSettings) {
    this.ctx.surfaces.post(surfaceId, { kind: "animation.settings", leaseId: load.lease_id, settings });
  }
}
