import { BridgeError } from "../shared/bridgeInvoke";

/** Stable error shared by plugin management, own RPCs and cooperative peers. */
export class PluginBridgeError extends BridgeError {
  constructor(message: string, code: string, details?: Record<string, unknown>) {
    super(message, code, details);
    this.name = "PluginBridgeError";
  }
}
