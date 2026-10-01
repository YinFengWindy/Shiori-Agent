/**
 * One event delivered over the desktop bridge. Plugin event handlers receive
 * it as their second argument, next to its already-extracted `payload`.
 */
export type BridgeEvent = {
  /** Owning plugin runtime generation; host events omit this field. */
  pluginGeneration?: string;
  id: string;
  type: "event";
  method: string;
  payload: Record<string, unknown>;
};

/** Handler for one plugin-local event name. */
export type PluginEventHandler = (payload: Record<string, unknown>, event: BridgeEvent) => void;

/** One background method returns a JSON-compatible value or propagates its failure. */
export type PluginBackgroundHandler = (payload: Record<string, unknown>) => unknown | Promise<unknown>;

/** A declared peer uses the same local call/event names as the owning plugin. */
export type PluginPeer = {
  call<T>(name: string, payload?: Record<string, unknown>, options?: { timeoutMs?: number }): Promise<T>;
  events: { on(name: string, handler: PluginEventHandler): Promise<() => void> };
  background: { call<T = void>(name: string, payload?: Record<string, unknown>): Promise<T> };
};

/**
 * The injected `client` every plugin UI, surface and background receives:
 * namespace-bound calls, events, declared peers and background requests.
 * Namespace binding is cooperation, not a sandbox or authentication.
 */
export type PluginRpcClient = PluginPeer & {
  dependency(pluginId: string): Promise<PluginPeer | null>;
  /** Only the background host enables registrations on the injected context. */
  handle(name: string, handler: PluginBackgroundHandler): Promise<void>;
  dispose(): Promise<void>;
};
