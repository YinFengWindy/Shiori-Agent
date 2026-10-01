import { BridgeError } from "@shiori/sdk";

/** The renderer-side desktop bridge's `invoke` function, shared by every per-domain client. */
export type DesktopInvoke = typeof window.miraDesktop.invoke;

/**
 * Invokes one bridge method and unwraps its payload, throwing `errorClass`
 * on an error envelope. Every per-domain bridge client (`plugin.*`,
 * `stories.*`, ...) otherwise re-implemented this exact
 * invoke-then-unwrap-or-throw shape identically.
 */
export async function invokeBridgePayload<T>(
  invoke: DesktopInvoke,
  method: string,
  payload: Record<string, unknown>,
  errorClass: new (message: string, code: string, details?: Record<string, unknown>) => Error = BridgeError,
  options?: { timeoutMs?: number },
): Promise<T> {
  const response = await invoke({ method, payload, ...options });
  if (response.error) throw new errorClass(response.error.message, response.error.code, response.error.details);
  return response.payload as T;
}
