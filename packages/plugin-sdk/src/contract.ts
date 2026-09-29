/**
 * `@shiori/plugin-sdk/contract`: the SDK's React- and DOM-free contract types,
 * for host code compiled outside the renderer (the Electron main process and
 * preload, whose TypeScript programs have neither JSX nor the DOM library and
 * so cannot load the main entry's components).
 *
 * Type-only: it has no runtime presence and is not part of the renderer import
 * map. Plugins import the same types from the main entry.
 */
export type { NativeFilePickerOptions } from "./contract/filePicker";
export type { BridgeEvent, PluginBackgroundHandler, PluginEventHandler, PluginPeer, PluginRpcClient } from "./rpc";
