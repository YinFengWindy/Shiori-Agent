import type React from "react";
import { normalizeChatAttachmentPaths } from "../chat/chatComposerState";
import type { AppMainView, ChatReplyTarget, RoleRecord, SessionPayload } from "../shared/types";

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
  setNotice: React.Dispatch<React.SetStateAction<string>>;
  setError: React.Dispatch<React.SetStateAction<string>>;
  setPendingChatAttachments: React.Dispatch<React.SetStateAction<string[]>>;
  setChatReplyTarget: React.Dispatch<React.SetStateAction<ChatReplyTarget | null>>;
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
  setNotice,
  setError,
  setPendingChatAttachments,
  setChatReplyTarget,
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

  async function pickChatAttachments(): Promise<void> {
    const files = await window.miraDesktop.pickChatAttachments({ multiple: true });
    if (!files.length) {
      return;
    }
    setPendingChatAttachments((current) => normalizeChatAttachmentPaths([...current, ...files]));
  }

  function beginAttachmentDrag(path: string): void {
    const normalizedPath = path.trim();
    if (!normalizedPath) {
      return;
    }
    window.miraDesktop.startAttachmentDrag({ path: normalizedPath });
  }

  function removePendingChatAttachment(path: string): void {
    setPendingChatAttachments((current) => current.filter((item) => item !== path));
  }

  async function copyChatMessage(content: string): Promise<void> {
    const normalizedContent = content.trim();
    if (!normalizedContent) {
      setNotice("当前消息没有可复制的文本。");
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
      setNotice("已复制消息。");
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
    }
  }

  function quoteChatMessage(target: ChatReplyTarget): void {
    setChatReplyTarget((current) => (
      current
      && current.messageId === target.messageId
      && current.content === target.content
      && current.sender === target.sender
        ? current
        : target
    ));
  }

  function clearChatReplyTarget(): void {
    setChatReplyTarget((current) => (current ? null : current));
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
      const target = Array.from(document.querySelectorAll<HTMLElement>("[data-message-key]"))
        .find((item) => item.dataset.messageKey === normalizedMessageKey);
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  return {
    openRoleDetail,
    openRoleAssets,
    pickChatAttachments,
    beginAttachmentDrag,
    removePendingChatAttachment,
    copyChatMessage,
    quoteChatMessage,
    clearChatReplyTarget,
    jumpToChatMessage,
  };
}
