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
    activeSession?: SessionPayload;
    currentMood?: string;
    moodIllustrationUrl?: string;
    chatLatestImageSidebarCollapsed?: boolean;
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
      chatLatestImageSidebarCollapsed={options.chatLatestImageSidebarCollapsed ?? true}
      chatLatestImageSidebarCount={options.chatLatestImageSidebarCollapsed === false ? 1 : 0}
      chatLatestImageSidebarWidth={320}
      currentMood={options.currentMood ?? ""}
      moodIllustrationBindingHit={false}
      moodIllustrationUrl={options.moodIllustrationUrl ?? ""}
      hasMoodIllustrationBinding={false}
      roleSelfView="我最近会不自觉地想起你。"
      relationshipTags={["亲近", "等你主动"]}
      lonelinessValue={72}
      conversationEndRef={React.createRef<HTMLDivElement>()}
      headerTitle={activeRole?.name ?? "Mira"}
      highlightedMessageKey=""
      notice=""
      sending={false}
      visibleIllustrationUrl=""
      onBeginChatLatestImageSidebarResize={() => undefined}
      onGoToNextChatImage={() => undefined}
      onGoToPreviousChatImage={() => undefined}
      onOpenChatImageLightbox={() => undefined}
      onOpenChatImagePreview={() => undefined}
      onOpenRoleDetail={() => undefined}
      onJumpToMessage={() => undefined}
      onBeginAttachmentDrag={() => undefined}
      onCopyMessage={() => undefined}
      onSendMessage={async () => true}
      onToggleChatLatestImageSidebar={() => undefined}
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

  it("renders persisted reply previews inside message bubbles", () => {
    const session = createSession();
    session.messages = [
      {
        role: "user",
        content: "继续",
        metadata: {
          reply_to_message_id: "message-1",
          reply_to_sender: "Mira",
          reply_to_content: "她停顿了一下，然后把声音放轻。",
        },
      },
    ];

    const markup = renderChatSurface(createRole(), "mira", { activeSession: session });

    assert.match(markup, />Mira</);
    assert.match(markup, />她停顿了一下，然后把声音放轻。</);
    assert.match(markup, />继续</);
    assert.match(markup, /aria-label="跳转到被引用消息"/);
  });

  it("keeps DOM lookup keys pinned to persisted message ids even when render ids exist", () => {
    const session = createSession();
    session.messages = [
      {
        id: "message-1",
        render_id: "local:user:1",
        role: "user",
        content: "继续",
      },
    ];

    const markup = renderChatSurface(createRole(), "mira", { activeSession: session });

    assert.match(markup, /data-message-key="message-1"/);
  });

  it("keeps message rows on a fixed-width track so long content does not shift the whole row", () => {
    const session = createSession();
    session.messages = [
      {
        role: "assistant",
        content: "这是一条很长很长的消息，用来确认消息行本身不会跟着气泡内容宽度一起伸缩。",
      },
      {
        role: "user",
        content: "我这边也来一条很长的消息，确认右侧气泡仍然只是在固定轨道里对齐。",
      },
    ];

    const markup = renderChatSurface(createRole(), "mira", { activeSession: session });

    assert.match(markup, /class="group w-full"/);
    assert.match(markup, /message-row flex w-full items-start gap-3/);
    assert.match(markup, /message-body flex min-w-0 w-full max-w-\[82%\] flex-col text-sm leading-6 text-\[#1f1f1f\]/);
    assert.match(markup, /ml-auto items-end/);
  });

  it("marks sent attachments as draggable so they can be dragged out of the desktop app", () => {
    const session = createSession();
    session.messages = [
      {
        role: "assistant",
        content: "",
        media: ["D:\\files\\scene.png", "D:\\files\\notes.md"],
      },
    ];

    const markup = renderChatSurface(createRole(), "mira", { activeSession: session });

    assert.match(markup, /draggable="true"/);
    assert.match(markup, /scene\.png/);
    assert.match(markup, /notes\.md/);
  });

  it("keeps the status tab disabled and falls back to images when no status illustration exists", () => {
    const markup = renderChatSurface(createRole(), "mira", {
      currentMood: "开心",
      moodIllustrationUrl: "",
      chatLatestImageSidebarCollapsed: false,
    });

    assert.match(markup, /aria-label="图片侧栏"/);
    assert.match(markup, /aria-label="状态侧栏"/);
    assert.match(markup, /justify-self-center inline-flex/);
    assert.match(markup, /h-7 w-7/);
    assert.match(markup, /disabled=""/);
    assert.doesNotMatch(markup, />使用回退立绘</);
  });

  it("keeps the image tab available when a status illustration exists", () => {
    const markup = renderChatSurface(createRole(), "mira", {
      currentMood: "开心",
      moodIllustrationUrl: "mira-asset://local?path=D%3A%5Croles%5Cmira%5Chappy.png",
      chatLatestImageSidebarCollapsed: false,
    });

    assert.match(markup, /aria-label="图片侧栏"/);
    assert.match(markup, /aria-label="状态侧栏"/);
    assert.doesNotMatch(markup, /aria-label="状态侧栏"[^>]*disabled=""/);
  });

  it("renders relationship summary, tags, and loneliness value inside the status sidebar", () => {
    const markup = renderChatSurface(createRole(), "mira", {
      currentMood: "开心",
      moodIllustrationUrl: "mira-asset://local?path=D%3A%5Croles%5Cmira%5Chappy.png",
      chatLatestImageSidebarCollapsed: false,
    });

    assert.match(markup, />当下想法</);
    assert.match(markup, />我最近会不自觉地想起你。</);
    assert.match(markup, />亲近</);
    assert.match(markup, />等你主动</);
    assert.match(markup, />寂寞值</);
    assert.match(markup, />72</);
  });
});
