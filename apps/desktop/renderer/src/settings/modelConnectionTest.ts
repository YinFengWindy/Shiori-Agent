import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { invokeBridgePayload, type DesktopInvoke } from "../shared/bridgeInvoke";

/** Outcome of one `models.test` probe, as reported by the bridge. */
export type ModelConnectionResult = { ok: true; latency_ms: number } | { ok: false; message: string };

/** What the fields show for the registration as it is right now. */
export type ModelConnectionTestView =
  | { status: "idle" }
  | { status: "testing" }
  | { status: "success"; latencyMs: number }
  | { status: "failure"; message: string };

/** A probe that belongs to one exact set of connection fields. */
export type ModelConnectionTestRecord = { key: string; view: ModelConnectionTestView };

/** Identifies the connection a probe exercised; effort and id do not affect reachability. */
export function modelConnectionKey(registration: ModelRegistrationFormData) {
  return JSON.stringify([registration.provider.trim(), registration.baseUrl.trim(), registration.apiKey.trim(), registration.model.trim()]);
}

/**
 * Resolves the visible state: a record only applies while the fields still
 * match what was probed, so editing any connection field returns to idle
 * without an effect resetting state.
 */
export function selectModelConnectionTestView(record: ModelConnectionTestRecord | null, registration: ModelRegistrationFormData): ModelConnectionTestView {
  if (!record || record.key !== modelConnectionKey(registration)) return { status: "idle" };
  return record.view;
}

/** Sends the unsaved draft to the bridge; nothing is persisted. */
export async function testModelConnection(invoke: DesktopInvoke, registration: ModelRegistrationFormData): Promise<ModelConnectionTestView> {
  const result = await invokeBridgePayload<ModelConnectionResult>(invoke, "models.test", {
    provider: registration.provider,
    model: registration.model,
    base_url: registration.baseUrl,
    api_key: registration.apiKey,
  });
  return result.ok ? { status: "success", latencyMs: result.latency_ms } : { status: "failure", message: result.message };
}
