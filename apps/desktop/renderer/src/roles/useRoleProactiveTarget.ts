import { useCallback, useEffect, useRef, useState } from "react";
import { invokeBridgePayload } from "../shared/bridgeInvoke";
import { errorMessage } from "../shared/feedback/feedbackStore";
import { mascotFeedback as feedback } from "../shared/mascot/mascotFeedback";
import type { RoleProactiveCandidate } from "../shared/types";
import { useLatestRef } from "../shared/useLatestRef";

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
const refreshEventMethods = new Set(["session.updated", "chat.done"]);

/**
 * The candidate the next proactive message would currently go to, for the
 * possibly unsaved candidate list. Reloads when the list changes, when a
 * session receives messages and when the window regains focus (the user is
 * back at the desktop); it never polls. A failed load clears the mark and
 * reports once through the shared feedback.
 */
export function useRoleProactiveTarget(
  roleId: string,
  candidates: RoleProactiveCandidate[],
  preview: RoleProactiveTargetPreview = previewRoleProactiveTarget,
) {
  const [target, setTarget] = useState<RoleProactiveCandidate | null>(null);
  // Responses may resolve out of order when edits arrive in a burst; only the latest request may publish.
  const requestRef = useRef(0);
  const candidatesRef = useLatestRef(candidates);
  // Compared by value: the form rebuilds the list on every binding keystroke.
  const candidatesKey = JSON.stringify(candidates);

  const reload = useCallback(async () => {
    const request = ++requestRef.current;
    const current = candidatesRef.current;
    if (!roleId || !current.length) {
      setTarget(null);
      return;
    }
    try {
      const next = await preview(roleId, current);
      if (request === requestRef.current) setTarget(next);
    } catch (error) {
      if (request !== requestRef.current) return;
      setTarget(null);
      feedback.error(`主动推送接收会话加载失败：${errorMessage(error)}`);
    }
  }, [roleId, candidatesRef, preview]);

  useEffect(() => { void reload(); }, [reload, candidatesKey]);

  useEffect(() => {
    const offEvents = window.miraDesktop.onEvent((event) => {
      if (refreshEventMethods.has(event.method)) void reload();
    });
    const handleFocus = () => { void reload(); };
    window.addEventListener("focus", handleFocus);
    return () => {
      offEvents();
      window.removeEventListener("focus", handleFocus);
    };
  }, [reload]);

  return target;
}
