import type { DesktopBridgeClient } from "../bridgeClient.js";
import type { BridgeEvent } from "../shared.js";

type RoleObservationBubbleTarget = {
  acceptRoleReply(roleId: string, reply: string): void;
};

/** Shows final desktop replies from the role bound to the visible pet. */
export function wireRoleReplyBubbles(
  bridge: DesktopBridgeClient,
  target: RoleObservationBubbleTarget,
): void {
  bridge.on("event", (event: BridgeEvent) => {
    if (event.method !== "chat.done") return;
    const roleId = typeof event.payload.role_id === "string" ? event.payload.role_id : "";
    const reply = typeof event.payload.reply === "string" ? event.payload.reply : "";
    if (roleId && reply.trim()) target.acceptRoleReply(roleId, reply);
  });
}
