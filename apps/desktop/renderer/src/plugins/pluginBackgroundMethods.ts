import { errorFeedback } from "@yinfengwindy/shiori-sdk/host-internal";
import { type BridgeEvent, type PluginBackgroundHandler, PluginBridgeError } from "@yinfengwindy/shiori-sdk";

/** Owns renderer handlers independently of the client transport/session lifetime. */
export class PluginBackgroundMethods {
  private readonly handlers = new Map<string, PluginBackgroundHandler>();

  /** Registers exactly once; failed transport registration cannot leave a local handler. */
  async register(name: string, handler: PluginBackgroundHandler, publish: () => Promise<unknown>) {
    if (this.handlers.has(name)) throw new PluginBridgeError("插件后台方法已注册", "plugin_method_exists");
    this.handlers.set(name, handler);
    try { await publish(); }
    catch (error) { this.handlers.delete(name); throw error; }
  }

  /** Cuts off new dispatch immediately while an already-running callback may drain. */
  clear() { this.handlers.clear(); }

  /** Replies only while this exact handler registration still owns the request. */
  async dispatch(event: BridgeEvent, isCurrent: () => boolean, reply: (value: Record<string, unknown>) => Promise<unknown>) {
    const handler = this.handlers.get(String(event.payload.name));
    if (!handler) return;
    let result: Record<string, unknown>;
    try { result = { result: await handler((event.payload.payload ?? {}) as Record<string, unknown>) }; }
    catch (error) {
      const failure = errorFeedback(error, "插件后台执行失败");
      result = { error: { code: error instanceof PluginBridgeError ? error.code : "plugin_handler_failed", message: failure.message, details: { detail: failure.detail } } };
    }
    if (isCurrent()) await reply({ ...result, request_id: event.payload.request_id });
  }
}
