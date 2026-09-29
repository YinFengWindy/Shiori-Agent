import { useState } from "react";
import type { RoleRecord } from "@shiori/plugin-sdk";
import { phoneChatInfoSections, phoneSubpageBack, type PhoneChatSubpage } from "./phoneChatInfo";
import { PhoneChatInfoPage } from "./PhoneChatInfoPage";
import { PhoneChatPage } from "./PhoneChatPage";
import type { PhoneConversation } from "./phoneClient";
import { PhoneMemberProfilePage } from "./PhoneMemberProfilePage";
import type { PhoneApp } from "./phonePresentation";

type SubpageView = { page: PhoneChatSubpage | null; direction: "forward" | "back" };

/**
 * One conversation's screens: its chat page, with the chat info page and
 * member profiles stacked over it. The chat page stays mounted beneath them
 * (hidden), so going back finds it where it was, still live. A conversation
 * without a chat info page (the user's own chat) offers neither.
 */
export function PhoneConversationScreens({ role, app, conversation, now, onBack }: {
  role: Pick<RoleRecord, "id" | "name" | "avatar_abs">;
  /** The app (account) the conversation was opened from. */
  app: PhoneApp;
  conversation: PhoneConversation;
  now: Date;
  /** Back from the chat page to the conversation list. */
  onBack: () => void;
}) {
  const [view, setView] = useState<SubpageView>({ page: null, direction: "forward" });
  const sections = phoneChatInfoSections(conversation);
  const open = (page: PhoneChatSubpage) => setView({ page, direction: "forward" });
  const back = () => setView((current) => ({ page: current.page && phoneSubpageBack(current.page), direction: "back" }));
  const { page } = view;
  return (
    <div className="relative h-full">
      <div className={page ? "invisible h-full" : "h-full"} inert={Boolean(page)}>
        <PhoneChatPage role={role} conversation={conversation} now={now} onBack={onBack}
          onOpenInfo={sections.length ? () => open({ kind: "info" }) : undefined}
          onOpenMember={(senderId) => open({ kind: "member", senderId, from: "chat" })} />
      </div>
      {page ? (
        <div key={page.kind === "member" ? `member:${page.senderId}` : "info"}
          className="phone-view absolute inset-0" data-direction={view.direction}>
          {page.kind === "info" ? (
            <PhoneChatInfoPage roleId={role.id} app={app} conversation={conversation} sections={sections} onBack={back}
              onOpenMember={(senderId) => open({ kind: "member", senderId, from: "info" })} />
          ) : (
            <PhoneMemberProfilePage roleId={role.id} threadId={conversation.threadId} senderId={page.senderId}
              backLabel={page.from === "info" ? "返回聊天信息" : "返回聊天"} onBack={back} />
          )}
        </div>
      ) : null}
    </div>
  );
}
