/**
 * Error thrown when a bridge call returns an error envelope; carries the
 * envelope's stable `code` and optional structured `details` next to the
 * human-readable message.
 */
export class BridgeError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "BridgeError";
  }
}

/**
 * Stable error shared by plugin management, a plugin's own RPCs and
 * cooperative peers. Plugins match it with `instanceof`, which only works
 * because the host and every plugin see this single class: built-in plugins
 * compile against it and external plugins receive it as a host peer.
 */
export class PluginBridgeError extends BridgeError {
  constructor(message: string, code: string, details?: Record<string, unknown>) {
    super(message, code, details);
    this.name = "PluginBridgeError";
  }
}
