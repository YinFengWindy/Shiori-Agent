import type React from "react";
import { findChatMessageElement } from "../chat/chatMessageDom";
import { prefersReducedMotion } from "../shared/reducedMotion";
import type { AppMainView, RoleRecord, SessionPayload } from "../shared/types";
import { errorMessage, type FeedbackReporter } from "../shared/feedback/feedbackStore";

type UseChatInteractionsArgs = {
  activeRoleId: string;
  roles: RoleRecord[];
  activeSessionRef: React.MutableRefObject<SessionPayload | null>;
  mainViewRef: React.MutableRefObject<AppMainView>;
  applyRoleSnapshot: (role: RoleRecord, sessionOverride?: SessionPayload | null) => void;
  openRoleWorkspace: (
    nextView: Extract<AppMainView, { kind: "role-detail" | "role-assets" }>,
    options?: { recordHistory?: boolean },
  ) => void;
  openRole: (roleId: string, roleOverride?: RoleRecord | null, options?: { recordHistory?: boolean }) => Promise<boolean>;
  feedback: FeedbackReporter;
  setHighlightedMessageKey: React.Dispatch<React.SetStateAction<string>>;
};

/** Owns chat-scoped desktop actions that do not need to live in the root component. */
export function useChatInteractions({
  activeRoleId,
  roles,
  activeSessionRef,
  mainViewRef,
  applyRoleSnapshot,
  openRoleWorkspace,
  openRole,
  feedback,
  setHighlightedMessageKey,
}: UseChatInteractionsArgs) {
  async function openRoleDetail(roleId: string): Promise<void> {
    const role = roles.find((item) => item.id === roleId) ?? null;
    if (role) {
      applyRoleSnapshot(role);
    }
    openRoleWorkspace({ kind: "role-detail", roleId });
    void openRole(roleId, role, { recordHistory: false });
  }

  async function openRoleAssets(roleId: string): Promise<void> {
    const role = roles.find((item) => item.id === roleId) ?? null;
    const currentView = mainViewRef.current;
    const sameRoleWorkspace =
      (currentView.kind === "role-detail" || currentView.kind === "role-assets")
      && currentView.roleId === roleId;
    if (role && !sameRoleWorkspace && activeRoleId !== roleId) {
      applyRoleSnapshot(role);
    }
    openRoleWorkspace({ kind: "role-assets", roleId });
    if (!sameRoleWorkspace && (activeSessionRef.current === null || activeRoleId !== roleId)) {
      void openRole(roleId, role, { recordHistory: false });
    }
  }

  function beginAttachmentDrag(path: string): void {
    const normalizedPath = path.trim();
    if (!normalizedPath) {
      return;
    }
    window.miraDesktop.startAttachmentDrag({ path: normalizedPath });
  }

  async function copyChatMessage(content: string): Promise<void> {
    const normalizedContent = content.trim();
    if (!normalizedContent) {
      feedback.info("这条消息没有可复制的文字");
      return;
    }
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(normalizedContent);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = normalizedContent;
        textarea.style.position = "fixed";
        textarea.style.left = "-9999px";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
      }
      feedback.success("已复制");
    } catch (error) {
      feedback.error(`复制失败：${errorMessage(error)}`);
    }
  }

  function jumpToChatMessage(messageKey: string): void {
    const normalizedMessageKey = messageKey.trim();
    if (!normalizedMessageKey) {
      return;
    }
    setHighlightedMessageKey((current) => (
      current === normalizedMessageKey ? "" : current
    ));
    window.requestAnimationFrame(() => {
      setHighlightedMessageKey(normalizedMessageKey);
      const target = findChatMessageElement(normalizedMessageKey);
      target?.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "center" });
    });
  }

  return {
    openRoleDetail,
    openRoleAssets,
    beginAttachmentDrag,
    copyChatMessage,
    jumpToChatMessage,
  };
}
