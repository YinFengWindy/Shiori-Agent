import { useState } from "react";
import type { RoleRecord } from "@shiori/plugin-sdk";
import { cx } from "@shiori/plugin-sdk";
import { phoneChatInfoSections, phoneSubpageBack, type PhoneChatSubpage } from "./phoneChatInfo";
import { PhoneChatInfoPage } from "./PhoneChatInfoPage";
import { PhoneChatPage } from "./PhoneChatPage";
import type { PhoneConversation } from "./phoneClient";
import { PhoneMemberProfilePage } from "./PhoneMemberProfilePage";
import type { PhoneApp } from "./phonePresentation";

type SubpageView = { page: PhoneChatSubpage | null; direction: "forward" | "back" };

/**
 * One conversation's screens: its chat page, with the chat info page and
 * member profiles stacked over it. Each screen stays mounted (hidden) under
 * the ones opened from it, so going back finds it as it was: the chat still
 * live, the info page with its unsaved note. A conversation
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
  // Bumped after a profile is saved or deleted, so the info page's member list rereads.
  const [membersRevision, setMembersRevision] = useState(0);
  const open = (page: PhoneChatSubpage) => setView({ page, direction: "forward" });
  const back = () => setView((current) => ({ page: current.page && phoneSubpageBack(current.page), direction: "back" }));
  const { page, direction } = view;
  // The info page stays mounted under a profile opened from it, keeping its unsaved note.
  const infoOpen = page !== null && (page.kind === "info" || page.from === "info");
  const member = page?.kind === "member" ? page : null;
  return (
    <div className="relative h-full">
      <div className={page ? "invisible h-full" : "h-full"} inert={Boolean(page)}>
        <PhoneChatPage role={role} conversation={conversation} now={now} onBack={onBack}
          onOpenInfo={sections.length ? () => open({ kind: "info" }) : undefined}
          onOpenMember={(senderId) => open({ kind: "member", senderId, from: "chat" })} />
      </div>
      {infoOpen ? (
        <div className={cx("phone-view absolute inset-0", member && "invisible")} inert={Boolean(member)}
          data-direction={member ? undefined : direction}>
          <PhoneChatInfoPage roleId={role.id} roleName={role.name} app={app} conversation={conversation} sections={sections}
            active={!member} membersRevision={membersRevision} now={now} onBack={back}
            onOpenMember={(senderId) => open({ kind: "member", senderId, from: "info" })} />
        </div>
      ) : null}
      {member ? (
        <div key={member.senderId} className="phone-view absolute inset-0" data-direction={direction}>
          <PhoneMemberProfilePage roleId={role.id} threadId={conversation.threadId} senderId={member.senderId}
            backLabel={member.from === "info" ? "返回聊天信息" : "返回聊天"} onBack={back}
            onChanged={() => setMembersRevision((revision) => revision + 1)} />
        </div>
      ) : null}
    </div>
  );
}
