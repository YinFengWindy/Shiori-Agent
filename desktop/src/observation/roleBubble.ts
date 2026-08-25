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
    if (!session || typeof session !== "object") return;
    const sessionValue = session as {
      metadata?: unknown;
      messages?: unknown;
    };
    const metadata = sessionValue.metadata;
    const roleId = metadata && typeof metadata === "object"
      && typeof (metadata as { role_id?: unknown }).role_id === "string"
      ? (metadata as { role_id: string }).role_id
      : "";
    const messages = sessionValue.messages;
    if (!Array.isArray(messages) || messages.length === 0) return;
    const lastMessage = messages[messages.length - 1];
    if (!lastMessage || typeof lastMessage !== "object") return;
    const message = lastMessage as {
      role?: unknown;
      content?: unknown;
      metadata?: unknown;
      proactive?: unknown;
    };
    const messageMetadata = message.metadata;
    const proactive = message.proactive === true
      || (messageMetadata && typeof messageMetadata === "object"
        && (messageMetadata as { proactive?: unknown }).proactive === true);
    if (message.role !== "assistant" || !proactive) return;
    const reply = typeof message.content === "string" ? message.content : "";
    publishReply(target, roleId, reply);
  });
}

function publishReply(target: RoleObservationBubbleTarget, roleId: string, reply: string): void {
    if (roleId && reply.trim()) target.acceptRoleReply(roleId, reply);
}
