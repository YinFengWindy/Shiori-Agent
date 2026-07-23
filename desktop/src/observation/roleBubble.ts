import type { DesktopBridgeClient } from "../bridgeClient.js";
import type { BridgeEvent } from "../shared.js";

type RoleObservationBubbleTarget = {
  acceptRoleObservationReply(roleId: string, reply: string): void;
};

/** Shows the role's final reply only after that role actually used observe_screen. */
export function wireRoleObservationBubbles(
  bridge: DesktopBridgeClient,
  target: RoleObservationBubbleTarget,
): void {
  bridge.on("event", (event: BridgeEvent) => {
    if (event.method !== "chat.done") return;
    const toolsUsed = event.payload.tools_used;
    if (!Array.isArray(toolsUsed) || !toolsUsed.includes("observe_screen")) return;
    const roleId = typeof event.payload.role_id === "string" ? event.payload.role_id : "";
    const reply = typeof event.payload.reply === "string" ? event.payload.reply : "";
    if (roleId && reply.trim()) target.acceptRoleObservationReply(roleId, reply);
  });
}
