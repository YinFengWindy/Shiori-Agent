import type { PluginRpcClient } from "../rpc";

function notFaked(name: string) {
  return () => Promise.reject(new Error(`fake plugin client: ${name} is not faked`));
}

/**
 * The injected `client` for plugin tests, with no bridge behind it: pass the
 * parts the component under test uses (usually `call`, answering by local
 * method name). Any other request fails loudly instead of silently
 * succeeding; `dispose` resolves.
 */
export function createFakePluginClient(overrides: Partial<PluginRpcClient> = {}): PluginRpcClient {
  return {
    services: { list: notFaked("services.list"), call: notFaked("services.call") },
    call: notFaked("call"),
    events: { on: notFaked("events.on") },
    background: { call: notFaked("background.call") },
    dependency: notFaked("dependency"),
    handle: notFaked("handle"),
    dispose: () => Promise.resolve(),
    ...overrides,
  };
}
