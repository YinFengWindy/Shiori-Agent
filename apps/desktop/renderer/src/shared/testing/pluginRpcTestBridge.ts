import type { DesktopInvoke } from "../bridgeInvoke";
import { createPluginRpcClient } from "../../plugins/pluginBridgeClient";

/** One plugin RPC the fake bridge received, without the injected plugin context. */
export type PluginRpcTestCall = { pluginId: string; name: string; params: Record<string, unknown> };

/** Answers one plugin RPC; throwing (or rejecting) becomes a failed call. */
export type PluginRpcTestResponder = (name: string, params: Record<string, unknown>, pluginId: string) => Record<string, unknown> | Promise<Record<string, unknown>>;

/**
 * Test-only desktop bridge: opens plugin communication contexts and routes
 * `plugin.<id>.<name>` calls to `respond`, recording each call.
 */
export function createPluginRpcTestInvoke(respond: PluginRpcTestResponder) {
  const calls: PluginRpcTestCall[] = [];
  const invoke: DesktopInvoke = async (request) => {
    const reply = (payload: Record<string, unknown>) => ({ id: "1", type: "response" as const, method: request.method, error: null, payload });
    if (request.method.startsWith("plugins.communication.")) return reply({ generation: "g1" });
    const match = /^plugin\.([^.]+)\.(.+)$/.exec(request.method);
    if (!match) throw new Error(`unexpected method: ${request.method}`);
    const [, pluginId, name] = match;
    const params = Object.fromEntries(Object.entries(request.payload).filter(([key]) => key !== "__plugin_context"));
    calls.push({ pluginId, name, params });
    return reply(await respond(name, params, pluginId));
  };
  return { invoke, calls };
}

/** A real plugin-scoped RPC client over the fake bridge. */
export function createPluginRpcTestClient(pluginId: string, respond: PluginRpcTestResponder) {
  const { invoke, calls } = createPluginRpcTestInvoke(respond);
  return { client: createPluginRpcClient(pluginId, invoke), calls };
}
