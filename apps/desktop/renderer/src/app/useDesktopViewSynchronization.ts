import type React from "react";
import { useEffect, useRef } from "react";
import type { AppMainView } from "../shared/types";

type UseDesktopViewSynchronizationArgs = {
  mainView: AppMainView;
  activeRoleId: string;
  setUnreadCounts: React.Dispatch<React.SetStateAction<Record<string, number>>>;
};

/** Synchronizes view-derived shell state without adding business effects to the renderer entrypoint. */
export function useDesktopViewSynchronization({
  mainView,
  activeRoleId,
  setUnreadCounts,
}: UseDesktopViewSynchronizationArgs) {
  const lastNonSettingsViewRef = useRef<AppMainView>({ kind: "chat" });

  useEffect(() => {
    if (mainView.kind !== "settings") {
      lastNonSettingsViewRef.current = mainView;
    }
  }, [mainView]);

  useEffect(() => {
    if (mainView.kind !== "chat" || !activeRoleId) {
      return;
    }
    setUnreadCounts((current) => {
      if (!current[activeRoleId]) {
        return current;
      }
      const next = { ...current };
      delete next[activeRoleId];
      return next;
    });
  }, [mainView.kind, activeRoleId, setUnreadCounts]);

  return lastNonSettingsViewRef;
}
