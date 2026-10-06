import type { PluginBackgroundContribution } from "@yinfengwindy/shiori-sdk";
import { VoicePreviewController } from "./preview";

/** Provider-owned playback, available without the desktop-pet plugin. */
const background: PluginBackgroundContribution = {
  pluginId: "gpt_sovits_tts",
  async setup(ctx) {
    const previews = new VoicePreviewController(ctx);
    ctx.effect("gpt_sovits_preview", () => previews.dispose());
    await ctx.rpc.handle("preview.play", (payload) => {
      if (typeof payload.id !== "string" || typeof payload.role_id !== "string" || typeof payload.audio_base64 !== "string" || (payload.format !== "wav" && payload.format !== "mp3")) throw new Error("试听参数无效");
      return previews.play(payload.id, payload.role_id, { audio_base64: payload.audio_base64, format: payload.format });
    });
    await ctx.rpc.handle("preview.status", () => previews.snapshot());
    await ctx.rpc.handle("preview.stop", (payload) => {
      if (typeof payload.id !== "string") throw new Error("试听标识无效");
      return previews.stop(payload.id);
    });
  },
};
export default background;
