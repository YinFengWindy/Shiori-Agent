import type { BridgeResponse } from "./shared.js";

/** Anything that can send one request over the desktop bridge. */
export interface BridgeInvoker {
  invoke(request: { method: string; payload: Record<string, unknown> }): Promise<BridgeResponse>;
}

/** Sends one bridge request and rejects with the backend's message when it answers with an error. */
export async function invokeBridgeOrThrow(
  bridge: BridgeInvoker,
  request: { method: string; payload: Record<string, unknown> },
) {
  const response = await bridge.invoke(request);
  if (response.error) {
    throw new Error(response.error.message);
  }
  return response.payload;
}
