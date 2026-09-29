/**
 * `@shiori/plugin-sdk`: the renderer contract between plugins and the Shiori
 * desktop host (#440).
 *
 * At runtime this entry is a host peer, like React: every value exported here
 * must also be listed in the renderer peer ABI
 * (`pluginUiPeerExports["@shiori/plugin-sdk"]` in
 * `apps/desktop/src/plugins/uiContract.ts`), and changing that list is a
 * runtime API change. This package must never import host source.
 */
export { BridgeError, PluginBridgeError } from "./errors";
export type { BridgeEvent, PluginBackgroundHandler, PluginEventHandler, PluginPeer, PluginRpcClient } from "./rpc";
