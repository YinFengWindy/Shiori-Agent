/**
 * The host services context is owned by `@shiori/plugin-sdk` (#505), so the
 * host, built-in plugins and external plugins (through the SDK peer) share
 * one context instance; re-exported for host callers.
 */
export { PluginHostServicesProvider, usePluginHostServices } from "@shiori/plugin-sdk";
