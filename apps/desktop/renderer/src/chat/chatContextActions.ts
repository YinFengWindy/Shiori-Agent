import { invokeBridgePayload } from "../shared/bridgeInvoke";
import { mascotFeedback as feedback } from "../shared/mascot/mascotFeedback";
import { contextResultFeedback, type ChatContextStatus } from "./chatContextState";

/** The same command-head normalization as the host, including bot addressing. */
export function isCompactCommand(content: string) {
  return content.trim().split(/\s+/, 1)[0]?.toLowerCase().split("@", 1)[0] === "/compact";
}

/** Execute and report one context transaction for the ring or a desktop send caller. */
export async function compactChatContext(roleId: string, isCurrent: () => boolean = () => true) {
  const result = await invokeBridgePayload<ChatContextStatus>(window.miraDesktop.invoke, "chat.context.compact", { role_id: roleId });
  if (isCurrent()) {
    const { message, detail } = contextResultFeedback(result);
    if (result.result?.committed) feedback.success(message);
    else feedback.error(message, { detail });
  }
  return result;
}
