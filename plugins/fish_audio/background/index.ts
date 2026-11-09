import type { PluginBackgroundContribution } from "@yinfengwindy/shiori-sdk";
import { PreviewPlayer } from "./preview";

/** Native preview playback is available even without desktop_pet. */
const background: PluginBackgroundContribution = {
  pluginId: "fish_audio",
  async setup(ctx) {
    const player = new PreviewPlayer(ctx.native.audio);
    ctx.effect("fish_audio_preview", () => player.dispose());
    await ctx.rpc.handle("preview.play", (payload) => {
      if (typeof payload.id !== "string" || typeof payload.audio_base64 !== "string" || payload.format !== "mp3") throw new Error("试听音频参数无效");
      return player.play(payload.id, { audio_base64: payload.audio_base64, format: "mp3" });
    });
    await ctx.rpc.handle("preview.status", () => player.snapshot());
    await ctx.rpc.handle("preview.stop", (payload) => {
      if (typeof payload.id !== "string") throw new Error("试听标识无效");
      return player.stop(payload.id);
    });
  },
};
export default background;
