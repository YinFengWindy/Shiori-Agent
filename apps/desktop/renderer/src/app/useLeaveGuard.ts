import { useCallback, useState } from "react";
import type { AppMainView } from "../shared/types";
import { useLatestRef } from "../shared/useLatestRef";

/**
 * Whether leaving the current view would drop unsaved role edits. The role
 * draft is shared by the detail and assets pages of one role (moving between
 * those two keeps it), so only navigation away from that pair is guarded —
 * and only while the draft differs from the saved role.
 */
export function shouldGuardRoleEditorLeave(mainView: AppMainView, roleFormDirty: boolean): boolean {
  return roleFormDirty && (mainView.kind === "role-detail" || mainView.kind === "role-assets");
}

/**
 * Holds a navigation intent back while `active`, until the user confirms
 * discarding or chooses to keep editing.
 *
 * Wraps whole navigation intents (a nav-rail click, back/forward, a search
 * result…) rather than the lower-level `setMainView`, because several intents
 * switch the active role *before* changing the view — deferring only the view
 * change would still let that role switch overwrite the draft.
 */
export function useLeaveGuard({ active, onDiscard }: { active: boolean; onDiscard: () => void }) {
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);
  const latest = useLatestRef({ active, onDiscard });

  /** Runs `action` now, or holds it for confirmation while the guard is active. Call it from event handlers. */
  const guard = useCallback((action: () => void) => {
    if (!latest.current.active) {
      action();
      return;
    }
    // Stored through the updater form: a bare function would be called as one.
    setPendingAction(() => action);
  }, [latest]);

  const confirmLeave = useCallback(() => {
    const action = pendingAction;
    setPendingAction(null);
    if (!action) return;
    latest.current.onDiscard();
    action();
  }, [latest, pendingAction]);

  const cancelLeave = useCallback(() => setPendingAction(null), []);

  return { guard, confirming: pendingAction !== null, confirmLeave, cancelLeave };
}
