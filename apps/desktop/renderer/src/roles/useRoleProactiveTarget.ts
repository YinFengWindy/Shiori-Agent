import { useCallback, useState } from "react";
import { invokeBridgePayload } from "../shared/bridgeInvoke";
import { errorMessage } from "../shared/feedback/feedbackStore";
import { mascotFeedback as feedback } from "../shared/mascot/mascotFeedback";
import type { RoleProactiveCandidate } from "../shared/types";
import { useBridgeRefreshedValue } from "../shared/useBridgeRefreshedValue";
import { roleProactiveCandidatesEqual } from "./roleProactiveCandidates";

/** Asks the backend which of these candidates the role's next proactive message would go to. */
export type RoleProactiveTargetPreview = (roleId: string, candidates: RoleProactiveCandidate[]) => Promise<RoleProactiveCandidate | null>;

/**
 * `roles.proactive.target`: the backend runs the same target selection as
 * delivery (desktop presence, latest user message per candidate), so the
 * renderer never re-implements the rule.
 */
export const previewRoleProactiveTarget: RoleProactiveTargetPreview = async (roleId, candidates) => {
  const payload = await invokeBridgePayload<{ target: RoleProactiveCandidate | null }>(
    window.miraDesktop.invoke,
    "roles.proactive.target",
    { role_id: roleId, candidates },
  );
  return payload.target;
};

/** New messages can change which candidate the user last wrote in. */
const refreshEvents: ReadonlySet<string> = new Set(["session.updated", "chat.done"]);

function reportPreviewError(error: unknown) {
  feedback.error(`主动推送接收会话加载失败：${errorMessage(error)}`);
}

/**
 * Keeps the previous list while the next one names the same sessions in the
 * same order: the form rebuilds the list on every binding keystroke, and only
 * a real change should ask the backend again.
 */
function useStableCandidates(candidates: RoleProactiveCandidate[]) {
  const [stable, setStable] = useState(candidates);
  if (!roleProactiveCandidatesEqual(stable, candidates)) {
    setStable(candidates);
    return candidates;
  }
  return stable;
}

/**
 * The candidate the next proactive message would currently go to, for the
 * possibly unsaved candidate list. Reloads when the list changes, when a
 * session receives messages and when the window regains focus (the user is
 * back at the desktop); a failed load clears the mark and reports once
 * through the shared feedback.
 */
export function useRoleProactiveTarget(
  roleId: string,
  candidates: RoleProactiveCandidate[],
  preview: RoleProactiveTargetPreview = previewRoleProactiveTarget,
) {
  const stableCandidates = useStableCandidates(candidates);
  const enabled = Boolean(roleId) && stableCandidates.length > 0;
  const load = useCallback(() => preview(roleId, stableCandidates), [preview, roleId, stableCandidates]);
  const { value } = useBridgeRefreshedValue({ enabled, load, refreshEvents, onError: reportPreviewError });
  return enabled ? value : null;
}
