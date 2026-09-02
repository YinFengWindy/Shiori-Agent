import type { DesktopBridgeClient } from "../bridge/bridgeClient.js";
import type { BridgeEvent } from "../bridge/shared.js";

type RoleObservationBubbleTarget = {
  acceptRoleReply(roleId: string, reply: string): void;
};

/** Shows final desktop replies from the role bound to the visible pet. */
export function wireRoleReplyBubbles(
  bridge: DesktopBridgeClient,
  target: RoleObservationBubbleTarget,
): void {
  bridge.on("event", (event: BridgeEvent) => {
    if (event.method === "chat.done") {
      const roleId = typeof event.payload.role_id === "string" ? event.payload.role_id : "";
      const reply = typeof event.payload.reply === "string" ? event.payload.reply : "";
      publishReply(target, roleId, reply);
      return;
    }
    if (event.method !== "session.updated" || event.id !== "proactive") return;
    const session = event.payload.session;
    const sessionValue = session && typeof session === "object"
      ? session as { metadata?: unknown; messages?: unknown }
      : null;
    const sessionMetadata = sessionValue?.metadata;
    const sessionRoleId = sessionMetadata && typeof sessionMetadata === "object"
      && typeof (sessionMetadata as { role_id?: unknown }).role_id === "string"
      ? (sessionMetadata as { role_id: string }).role_id
      : "";
    const roleId = typeof event.payload.role_id === "string"
      ? event.payload.role_id
      : sessionRoleId;

    // New incremental events carry the changed message directly. Keep the old
    // full-snapshot fallback for older bridge versions and persisted fixtures.
    const changedMessage = event.payload.message;
    const message = changedMessage && typeof changedMessage === "object"
      ? changedMessage
      : sessionValue?.messages && Array.isArray(sessionValue.messages)
        ? sessionValue.messages.at(-1)
        : null;
    if (!message || typeof message !== "object") return;
    const messageValue = message as {
      role?: unknown;
      content?: unknown;
      metadata?: unknown;
      proactive?: unknown;
    };
    const messageMetadata = messageValue.metadata;
    const proactive = messageValue.proactive === true
      || (messageMetadata && typeof messageMetadata === "object"
        && (messageMetadata as { proactive?: unknown }).proactive === true);
    if (messageValue.role !== "assistant" || !proactive) return;
    const reply = typeof messageValue.content === "string" ? messageValue.content : "";
    publishReply(target, roleId, reply);
  });
}

function publishReply(target: RoleObservationBubbleTarget, roleId: string, reply: string): void {
    if (roleId && reply.trim()) target.acceptRoleReply(roleId, reply);
}
