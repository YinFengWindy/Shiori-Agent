import type { BridgeEvent, SurfaceRoleActivity } from "@yinfengwindy/shiori-sdk/contract";
import { roleIdFromSessionKey } from "../bridge/sessionIdentity.js";

/** Translate host events once, exposing only role-scoped activity to surfaces. */
export function surfaceRoleActivity(event: BridgeEvent): SurfaceRoleActivity | null {
  const payload = event.payload;
  const session = object(payload.session);
  const metadata = object(session?.metadata);
  const sessionKey = string(payload.session_key) ?? string(session?.key);
  const roleId = string(payload.role_id) ?? string(metadata?.role_id)
    ?? (sessionKey ? roleIdFromSessionKey(sessionKey) : null);
  if (!roleId || !sessionKey) return null;
  if (event.method === "chat.delta") return { roleId, sessionKey, phase: "running", notify: false };
  if (event.method === "chat.done") return { roleId, sessionKey, phase: "review", notify: false };
  if (event.method === "chat.error") return { roleId, sessionKey, phase: "failed", notify: false };
  if (event.method !== "session.updated") return null;
  const messages = session?.messages;
  const message = object(payload.message) ?? object(Array.isArray(messages) ? messages.at(-1) : null);
  const notify = message?.role === "assistant" && object(message.metadata)?.proactive === true;
  return { roleId, sessionKey, phase: notify ? "waiting" : "review", notify };
}

function object(value: unknown): Record<string, unknown> | null {
  return isRecord(value) ? value : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function string(value: unknown): string | null {
  return typeof value === "string" && value ? value : null;
}
