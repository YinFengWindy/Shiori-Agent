import { errorMessage, PluginBridgeError, type PluginHostFeedback, type PluginRpcClient } from "@yinfengwindy/shiori-sdk";

/**
 * Release is best effort because the parent's scoped client may already be disposed.
 * Epoch checks separately prevent late synthesis from playing. Only the known local
 * disposal error is expected here; other failures go to host feedback after unmount.
 */
export async function releasePreview(client: PluginRpcClient, id: string, feedback: PluginHostFeedback) {
  try { await client.background.call("preview.stop", { id }); }
  catch (cause) {
    if (cause instanceof PluginBridgeError && cause.code === "plugin_unavailable" && cause.details?.reason === "context_disposed") return;
    feedback.error("停止试听失败", { detail: errorMessage(cause, { includeDetail: true }) });
  }
}
