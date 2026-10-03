import { useEffect } from "react";
import { errorMessage, useLatestRef } from "@yinfengwindy/shiori-sdk";
import type { FeedbackReporter } from "../shared/feedback/feedbackStore";

type NotificationNavigationOptions = {
  ready: boolean;
  guardNavigation(action: () => void): void;
  openChatView(options: { recordHistory: boolean }): void;
  openRole(roleId: string): Promise<boolean>;
  feedback: FeedbackReporter;
};

/** Opens clicked chats after bootstrap, preserving pending clicks and the existing unsaved-edit guard. */
export function useDesktopNotificationNavigation({ ready, ...callbacks }: NotificationNavigationOptions) {
  const latest = useLatestRef(callbacks);
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    let requestVersion = 0;
    let lastTargetId: number | null = null;
    const api = window.miraDesktop.notifications;
    const reportError = (error: unknown) => {
      if (!cancelled) latest.current.feedback.error(`打开通知会话失败：${errorMessage(error)}`);
    };
    async function navigate() {
      const version = ++requestVersion;
      const target = await api.getPending();
      if (cancelled || version !== requestVersion || !target || target.id === lastTargetId) return;
      lastTargetId = target.id;
      latest.current.guardNavigation(() => {
        if (cancelled || target.id !== lastTargetId) return;
        latest.current.openChatView({ recordHistory: false });
        void latest.current.openRole(target.roleId).then(async (opened) => {
          if (opened && !cancelled) await api.acknowledge(target.id);
        }).catch(reportError);
      });
    }
    const onClicked = () => { void navigate().catch(reportError); };
    // Subscribe before reading so a click between bootstrap and this effect cannot be lost.
    const unsubscribe = api.onClicked(onClicked);
    onClicked();
    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [latest, ready]);
}
