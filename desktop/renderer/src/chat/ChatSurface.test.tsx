/// <reference types="node" />

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ChatSurface } from "./ChatSurface";
import type { RoleRecord, SessionPayload } from "../shared/types";

function createRole(overrides: Partial<RoleRecord> = {}): RoleRecord {
  return {
    id: overrides.id ?? "mira",
    name: overrides.name ?? "Mira",
    description: overrides.description ?? "",
    system_prompt: overrides.system_prompt ?? "",
    runtime_config: overrides.runtime_config ?? {},
    avatar: overrides.avatar ?? "roles/assets/mira/avatar.png",
    avatar_abs: overrides.avatar_abs ?? "D:\\avatars\\mira.png",
    chat_background: overrides.chat_background ?? null,
    chat_background_abs: overrides.chat_background_abs ?? null,
    illustrations: overrides.illustrations ?? [],
    illustrations_abs: overrides.illustrations_abs ?? [],
    created_at: overrides.created_at ?? "2026-07-03T12:00:00+08:00",
    updated_at: overrides.updated_at ?? "2026-07-03T12:00:00+08:00",
  };
}

function createSession(): SessionPayload {
  return {
    key: "role:mira",
    created_at: "2026-07-03T12:00:00+08:00",
    updated_at: "2026-07-03T12:00:00+08:00",
    last_consolidated: 0,
    metadata: {},
    messages: [],
  };
}

function renderChatSurface(
  activeRole: RoleRecord | null,
  activeRoleId: string,
  options: {
    draft?: string;
    pendingChatAttachments?: string[];
    activeSession?: SessionPayload;
  } = {},
): string {
  return renderToStaticMarkup(
    <ChatSurface
      activeRole={activeRole}
      activeRoleId={activeRoleId}
      activeSession={options.activeSession ?? createSession()}
      bridgeReady
      chatLatestImagePath=""
      chatLatestImagePosition={0}
      chatLatestImageSidebarAnimating={false}
      chatLatestImageSidebarCollapsed
      chatLatestImageSidebarCount={0}
      chatLatestImageSidebarWidth={320}
      conversationEndRef={React.createRef<HTMLDivElement>()}
      draft={options.draft ?? ""}
      headerTitle={activeRole?.name ?? "Mira"}
      highlightedMessageKey=""
      notice=""
      pendingChatAttachments={options.pendingChatAttachments ?? []}
      sending={false}
      visibleIllustrationUrl=""
      onBeginChatLatestImageSidebarResize={() => undefined}
      onGoToNextChatImage={() => undefined}
      onGoToPreviousChatImage={() => undefined}
      onOpenChatImageLightbox={() => undefined}
      onOpenChatImagePreview={() => undefined}
      onPickChatAttachments={() => undefined}
      onOpenRoleDetail={() => undefined}
      onRemovePendingChatAttachment={() => undefined}
      onSendMessage={() => undefined}
      onToggleChatLatestImageSidebar={() => undefined}
      onUpdateDraft={() => undefined}
    />,
  );
}

describe("ChatSurface", () => {
  it("renders the header avatar as a role-detail button when an active role is present", () => {
    const markup = renderChatSurface(createRole(), "mira");

    assert.match(markup, /data-testid="chat-header-avatar-button"/);
    assert.match(markup, /aria-label="查看角色 Mira 详情"/);
  });

  it("keeps the header avatar non-interactive when there is no active role", () => {
    const markup = renderChatSurface(null, "");

    assert.doesNotMatch(markup, /data-testid="chat-header-avatar-button"/);
    assert.doesNotMatch(markup, /aria-label="查看角色 .* 详情"/);
  });

  it("renders image attachments as thumbnails and keeps text attachments as pending cards", () => {
    const markup = renderChatSurface(createRole(), "mira", {
      pendingChatAttachments: ["D:\\files\\scene.png", "D:\\files\\notes.md"],
    });

    assert.match(markup, /aria-label="添加附件"/);
    assert.match(markup, /mira-asset:\/\/local\?path=D%3A%5Cfiles%5Cscene\.png/);
    assert.doesNotMatch(markup, />scene\.png</);
    assert.match(markup, />notes\.md</);
    assert.match(markup, />MD</);
  });

  it("renders sent text attachments as compact file pills", () => {
    const session = createSession();
    session.messages = [
      {
        role: "assistant",
        content: "给你文件",
        media: ["D:\\files\\yinfeng-chat-history.md"],
      },
    ];

    const markup = renderChatSurface(createRole(), "mira", { activeSession: session });

    assert.match(markup, />yinfeng-chat-history\.md</);
    assert.doesNotMatch(markup, />附件</);
  });

  it("allows sending when attachments exist even if the draft is empty", () => {
    const markup = renderChatSurface(createRole(), "mira", {
      pendingChatAttachments: ["D:\\files\\notes.md"],
    });

    assert.match(markup, /aria-label="发送消息"/);
    assert.doesNotMatch(markup, /aria-label="发送消息"[^>]*disabled=""/);
  });
});
