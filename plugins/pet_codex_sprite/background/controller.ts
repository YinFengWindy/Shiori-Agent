import type { BackgroundCtx } from "@yinfengwindy/shiori-sdk";
import { emptyPetReply, isRecord, PetProviderController, readPresentationState, type PetProviderReport } from "@yinfengwindy/shiori-pet";
import { readSpriteState, type SpritePresentation } from "../shared/presentation";
import type { SpriteState } from "../surface/spriteContract";

type SpriteLoad = SpritePresentation & { actions: Record<string, SpriteState> };
/** Decodes sprite data and maps sprite animation names on the shared provider lifecycle. */
export class SpritePresentationController extends PetProviderController<SpriteLoad> {
  constructor(ctx: Pick<BackgroundCtx, "surfaces" | "assets" | "reportFailure">, report: (value: PetProviderReport) => Promise<unknown>) {
    super(ctx, {
      pluginId: "pet_codex_sprite", report,
      prepare(identity, value, assetUrl) {
        if (typeof value.spritesheet_abs !== "string" || !isRecord(value.body) || !isRecord(value.actions)) throw new Error("精灵模型数据无效");
        const spritesheetUrl = assetUrl(value.spritesheet_abs), { width, height } = value.body;
        if (!spritesheetUrl || typeof width !== "number" || typeof height !== "number" || !Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) throw new Error("精灵素材不可用");
        const actions: Record<string, SpriteState> = {};
        for (const [name, candidate] of Object.entries(value.actions)) { const state = readSpriteState(candidate); if (!state) throw new Error("精灵动作无效"); actions[name] = state; }
        const state = value.state === undefined ? { reply: emptyPetReply, voice: { status: "idle" as const } } : readPresentationState(value.state);
        if (!state) throw new Error("精灵展示状态无效");
        return { ...identity, spritesheetUrl, body: { width, height }, state, actions };
      },
      action(load, command, direction) {
        if (direction) return command.animation === "run" ? { state: direction === "left" ? "running-left" : "running-right", transient: true } : undefined;
        const state = typeof command.name === "string" ? load.actions[command.name] : undefined;
        if (!state) throw new Error("模型不支持该动作");
        return { state, transient: true };
      },
    });
  }
}
