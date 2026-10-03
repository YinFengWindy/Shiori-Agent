import { BridgeError, errorMessage } from "@yinfengwindy/shiori-sdk";
import type { DesktopSessionStateArgs } from "./desktopSessionTypes";
import type { useDesktopChatTurns } from "./useDesktopChatTurns";
import type { createDesktopSessionSnapshot } from "./desktopSessionSnapshot";
import { finalizeChatCancellation } from "../chat/chatStreamingState";
import { parseSessionMessageUpdatePayload } from "./desktopSessionProtocol";
import type { createDesktopSessionMessages } from "./desktopSessionMessages";
type Args = Pick<DesktopSessionStateArgs, "cancellingSessionsRef" | "feedback">
  & Pick<ReturnType<typeof useDesktopChatTurns>, "latestTurnIdsRef" | "markSessionCancelling" | "isCurrentChatTurn" | "completeChatTurn" | "clearSessionCancelling">
  & Pick<ReturnType<typeof createDesktopSessionSnapshot>, "updateCommittedActiveSession">
  & Pick<ReturnType<typeof createDesktopSessionMessages>, "commitSessionMessageUpdate">;
/** Cancels only the owning turn and reconciles its persisted interrupted trace. */
export function createDesktopChatCancellation({
  cancellingSessionsRef,
  feedback,
  latestTurnIdsRef,
  markSessionCancelling,
  isCurrentChatTurn,
  completeChatTurn,
  clearSessionCancelling,
  commitSessionMessageUpdate,
  updateCommittedActiveSession
}: Args) {
  async function cancelChatTurn(sessionKey: string, roleId: string): Promise<boolean> {
    const turnId = latestTurnIdsRef.current[sessionKey] ?? "";
    if (!isCurrentChatTurn(sessionKey, turnId)) return false;
    if (cancellingSessionsRef.current[sessionKey]) return false;
    markSessionCancelling(sessionKey, roleId);
    try {
      const res = await window.miraDesktop.invoke({
        method: "chat.cancel",
        payload: { session_key: sessionKey, turn_id: turnId },
      });
      if (res.error) throw new BridgeError(res.error.message, res.error.code, res.error.details);
      const status = String(res.payload.status ?? "");
      if (status !== "interrupted" && status !== "idle") {
        throw new Error(String(res.payload.message ?? "中止回复失败"));
      }
      if (isCurrentChatTurn(sessionKey, turnId)) {
        updateCommittedActiveSession((current) => current?.key === sessionKey
          ? finalizeChatCancellation(current, status as "interrupted" | "idle")
          : current);
        completeChatTurn(sessionKey, turnId);
        // Swap the transient interrupted trace for its persisted form so the
        // next turn's seq ordering does not sort around an id-less bubble.
        const update = parseSessionMessageUpdatePayload({
          session: res.payload.session,
          message: res.payload.message_payload,
        });
        if (update?.message && update.session.key === sessionKey) {
          commitSessionMessageUpdate(roleId, update);
        }
      }
      return true;
    } catch (error) {
      if (isCurrentChatTurn(sessionKey, turnId)) {
        clearSessionCancelling(sessionKey);
        feedback.error(errorMessage(error, { includeDetail: true }));
      }
      return false;
    }
  }

  return { cancelChatTurn };
}
