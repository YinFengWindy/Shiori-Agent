import { PluginBackgroundMethods, type PluginBackgroundHandler } from "./pluginBackgroundMethods";
import { pluginRuntimeChanged } from "./pluginRuntimeChanged";
import { PluginCommunicationLifetime } from "./pluginCommunicationLifetime";
import type { BridgeEvent } from "../../../src/bridge/shared";
import { invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";
import { PluginBridgeError as BridgeError } from "./pluginBridgeError";

type EventHandler = (payload: Record<string, unknown>, event: BridgeEvent) => void;

/** A declared peer uses the same local call/event names as the owning plugin. */
export type PluginPeer = {
  call<T>(name: string, payload?: Record<string, unknown>, options?: { timeoutMs?: number }): Promise<T>;
  events: { on(name: string, handler: EventHandler): Promise<() => void> };
  background: { call<T = void>(name: string, payload?: Record<string, unknown>): Promise<T> };
};

/** Injected cooperation API; namespace binding is not a sandbox or authentication. */
export type PluginCommunicationClient = PluginPeer & {
  dependency(pluginId: string): Promise<PluginPeer | null>;
  /** Only the background host enables registrations on the injected context. */
  handle(name: string, handler: PluginBackgroundHandler): Promise<void>;
  dispose(): Promise<void>;
};

/** Creates one disposable UI/surface/background context over the existing bridge. */
export function createPluginCommunicationClient(pluginId: string, options: {
  invoke?: DesktopInvoke;
  onEvent?: (listener: (event: BridgeEvent) => void) => () => void;
  background?: boolean;
} = {}): PluginCommunicationClient {
  const owner = crypto.randomUUID();
  const lifetime = new PluginCommunicationLifetime();
  const subscriptions = new Set<{ target: string; name: string; handler: EventHandler }>();
  const methods = new PluginBackgroundMethods();
  let generation: Promise<string> | undefined;
  let currentGeneration = "";
  let unsubscribe: (() => void) | undefined;
  let disposed = false;
  let closing: Promise<void> | undefined;
  const invoke = <T,>(method: string, payload: Record<string, unknown>, callOptions?: { timeoutMs?: number }) =>
    invokeBridgePayload<T>(options.invoke ?? window.miraDesktop.invoke, method, payload, BridgeError, callOptions);
  const assertActive = () => lifetime.assertActive();
  const connect = () => {
    assertActive();
    if (!generation) {
      unsubscribe ??= (options.onEvent ?? window.miraDesktop.onEvent)(onEvent);
      generation = invoke<{ generation: string }>("plugins.communication.open", { plugin_id: pluginId, owner })
        .then((result) => { if (!disposed) currentGeneration = result.generation; return result.generation; })
        .catch((error) => { generation = undefined; throw error; });
    }
    return lifetime.wait(generation);
  };
  const transport = async <T,>(operation: string, payload: Record<string, unknown> = {}) => {
    const token = await connect();
    assertActive();
    const result = await lifetime.wait(invoke<T>(`plugins.communication.${operation}`, {
      ...payload, plugin_id: pluginId, generation: token, owner,
    }, { timeoutMs: 20_000 }));
    assertActive();
    if (token !== currentGeneration) throw new BridgeError("插件运行代际已替换", "plugin_unavailable");
    return result;
  };
  const closeContext = (remote = true) => {
    if (closing) return closing;
    disposed = true;
    lifetime.dispose();
    unsubscribe?.();
    currentGeneration = "";
    subscriptions.clear();
    methods.clear();
    const opening = generation;
    closing = (async () => {
      if (!remote || !opening) return;
      // A publication may race an open served by the successor generation.
      // Close the actual returned token even after local admission has ended.
      const token = await opening.catch(() => "");
      if (token) await invoke("plugins.communication.close", { plugin_id: pluginId, owner, generation: token });
    })();
    return closing;
  };
  function onEvent(event: BridgeEvent) {
    if (pluginRuntimeChanged(event)) {
      // An exited process owns no contexts. Calling it to close one would
      // implicitly start a replacement bridge solely for cleanup.
      void closeContext(event.method !== "bridge.exit").catch(() => undefined);
      return;
    }
    if (disposed || !currentGeneration || event.pluginGeneration !== currentGeneration) return;
    if (event.method === `plugin.${pluginId}.__request` && event.payload.owner === owner) {
      // This is the transport boundary. Provider errors travel in the reply;
      // transport loss is observable by the caller's bounded request timeout.
      const token = currentGeneration;
      void methods.dispatch(event, () => !disposed && token === currentGeneration, (reply) => transport("reply", reply)).catch(() => undefined);
      return;
    }
    for (const entry of subscriptions) {
      if (event.method === `plugin.${entry.target}.${entry.name}`) entry.handler(event.payload, event);
    }
  }
  const peer = (target: string): PluginPeer => ({
    async call<T>(name: string, payload: Record<string, unknown> = {}, callOptions?: { timeoutMs?: number }) {
      validateName(name);
      const token = await connect();
      assertActive();
      const result = await lifetime.wait(invoke<T>(`plugin.${target}.${name}`, {
        ...payload, __plugin_context: { plugin_id: pluginId, generation: token },
      }, callOptions));
      assertActive();
      if (token !== currentGeneration) throw new BridgeError("插件运行代际已替换", "plugin_unavailable");
      return result;
    },
    events: { async on(name, handler) {
      validateName(name);
      const result = await transport<{ available: boolean }>("resolve", { target });
      if (!result.available) throw new BridgeError(`插件 ${target} 不可用`, "plugin_unavailable");
      const entry = { target, name, handler };
      subscriptions.add(entry);
      return () => { subscriptions.delete(entry); };
    } },
    background: { async call<T>(name: string, payload: Record<string, unknown> = {}) {
      validateName(name);
      const response = await transport<{ result: T }>("call", { target, name, payload });
      return response.result;
    } },
  });
  return {
    ...peer(pluginId),
    async dependency(target) {
      const result = await transport<{ available: boolean }>("resolve", { target });
      return result.available ? peer(target) : null;
    },
    async handle(name, handler) {
      if (!options.background) throw new BridgeError("仅后台可以注册方法", "plugin_invalid_registration");
      validateName(name);
      await methods.register(name, handler, () => transport("register", { name }));
    },
    dispose: closeContext,
  };
}

function validateName(name: string) {
  if (!/^[a-zA-Z]\w*(?:\.\w+)*$/.test(name) || name.startsWith("plugin.")) {
    throw new BridgeError("请使用插件内的局部名称", "plugin_invalid_name");
  }
}
