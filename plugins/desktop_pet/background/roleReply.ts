import type { BridgeEvent } from "../../../apps/desktop/src/bridge/shared";

/** Extracts a new role reply while ignoring ordinary session refreshes. */
export function readRoleReply(event: BridgeEvent) {
  const payload = event.payload;
  if (event.method === "chat.done") return reply(payload.role_id, payload.reply);
  if (event.method !== "session.updated" || event.id !== "proactive") return null;
  const session = record(payload.session);
  const sessionMetadata = record(session?.metadata);
  // Older snapshots carry the appended message last; incremental updates carry it directly.
  const message = record(payload.message)
    ?? (Array.isArray(session?.messages) ? record(session.messages.at(-1)) : null);
  if (!message || message.role !== "assistant") return null;
  if (message.proactive !== true && record(message.metadata)?.proactive !== true) return null;
  return reply(typeof payload.role_id === "string" ? payload.role_id : sessionMetadata?.role_id, message.content);
}

function reply(roleId: unknown, text: unknown) {
  return typeof roleId === "string" && roleId && typeof text === "string" && text.trim()
    ? { roleId, text: text.trim() }
    : null;
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" ? value as Record<string, unknown> : null;
}
