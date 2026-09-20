import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { BookOpen, SidebarSimple } from "@phosphor-icons/react";
import { NavRail } from "../shell/NavRail";
import { RoleSidebar } from "../roles/RoleSidebar";
import { ChatHeader } from "../chat/ChatHeader";
import { ChatMessageList } from "../chat/ChatMessageList";
import { ChatComposer } from "../chat/ChatComposer";
import { ChatStatusSidebar } from "../chat/ChatStatusSidebar";
import { ChatMessageContextMenu } from "../chat/ChatMessageContextMenu";
import { getVisibleChatMessages } from "../chat/chatMessageWindow";
import { iconButtonClass } from "../shared/styles";
import { demoAvatar, demoRole } from "./demoContent";
import type { createDemoChat } from "./demoChat";
import { useDemoMessageActions } from "./useDemoMessageActions";
import { useDemoSidebar } from "./useDemoSidebar";

const roles = [demoRole];
const noAction = () => undefined;
const capabilities = { attachments: false, modelSelection: false };

/** Mount the actual desktop chat surfaces with a clearly prewritten browser session. */
export function ShowcaseChat({ chat, onStory }: { chat: ReturnType<typeof createDemoChat>; onStory: () => void }) {
  const state = useSyncExternalStore(chat.subscribe, chat.getSnapshot);
  const [statusOpen, setStatusOpen] = useState(() => window.innerWidth >= 1000);
  const conversationEndRef = useRef<HTMLDivElement>(null);
  const conversationListRef = useRef<HTMLDivElement>(null);
  const actions = useDemoMessageActions();
  const sidebar = useDemoSidebar();
  useEffect(() => { conversationEndRef.current?.scrollIntoView({ block: "end" }); }, [state.messages]);
  return <div className="showcase-chat flex h-full min-h-0">
    <NavRail activeView="messages" unreadTotal={0} visibleBuiltins={["messages"]} onOpenSearch={noAction} onBackToChat={noAction} onOpenRolesWorkspace={noAction} onOpenSettings={noAction} pluginEntries={[{ pageId: "story", label: "故事", icon: BookOpen, onSelect: onStory }]} />
    <div className="showcase-roles shrink-0">
      <RoleSidebar roles={roles} activeRoleId={demoRole.id} unreadCounts={{}} bridgeReady collapsed={false} animating={false} width={sidebar.width} onOpenRole={noAction} onBeginResize={sidebar.beginResize} />
    </div>
    <main className="relative grid min-h-0 min-w-0 flex-1 grid-rows-chat overflow-hidden rounded-md border border-line-soft bg-surface-soft">
      <ChatHeader activeRole={demoRole} detailRole={null} title={demoRole.name} onOpenRoleDetail={noAction} />
      <button type="button" className={`${iconButtonClass} absolute right-3 top-2 z-[3]`} aria-label={statusOpen ? "收起角色状态" : "展开角色状态"} aria-expanded={statusOpen} onClick={() => setStatusOpen((open) => !open)}><SidebarSimple className="h-5 w-5" /></button>
      <div className="relative flex min-h-0 min-w-0">
        <div className="relative min-h-0 min-w-0 flex-1">
          <ChatMessageList activeRole={demoRole} sessionKey="demo:chat" conversationEndRef={conversationEndRef} conversationListRef={conversationListRef} highlightedMessageKey="" visibleMessageWindow={getVisibleChatMessages(state.messages, 160)} onBeginAttachmentDrag={noAction} onJumpToMessage={actions.jump} onOpenContextMenu={actions.openMenu} onOpenImagePreview={noAction} />
          <ChatComposer activeRoleId={demoRole.id} sessionKey="demo:chat" bridgeReady sending={state.sending} cancelling={false} replyTarget={actions.replyTarget} onSendMessage={chat.send} onCancelChat={chat.cancel} onClearReplyTarget={actions.clearReply} onJumpToMessage={actions.jump} capabilities={capabilities} />
          {state.error || actions.error ? <p role="alert" className="absolute inset-x-3 top-2 rounded-md bg-danger-soft px-3 py-2 text-body text-danger-text">{state.error || actions.error}</p> : null}
          <div className="pointer-events-none absolute inset-x-0 bottom-3 text-center text-caption text-ink-muted">预设回复 · 状态为演示样例</div>
        </div>
        {statusOpen ? <aside className="showcase-status w-64 shrink-0 p-3" aria-label="角色状态"><ChatStatusSidebar currentMood={state.mood} moodIllustrationUrl={demoAvatar} roleSelfView={state.thought} relationshipTags={["初次相识"]} lonelinessValue={8} /></aside> : null}
      </div>
    </main>
    {actions.menu ? <ChatMessageContextMenu menu={actions.menu} menuRef={actions.menuRef} sending={state.sending} onCopy={() => void actions.copy()} onQuote={actions.quote} /> : null}
  </div>;
}
