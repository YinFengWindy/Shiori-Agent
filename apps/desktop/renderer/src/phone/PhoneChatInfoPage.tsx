import type { ComponentType } from "react";
import type { PhoneChatInfoSection, PhoneChatInfoSectionId } from "./phoneChatInfo";
import { PhoneChatActivitySection, PhoneChatMembersSection, PhoneChatSummarySection, type PhoneChatInfoSectionProps } from "./PhoneChatInfoSections";
import type { PhoneConversation } from "./phoneClient";
import { PhoneGroupNoteSection } from "./PhoneGroupNoteSection";
import { PhoneListeningSection } from "./PhoneListeningSection";
import type { PhoneApp } from "./phonePresentation";
import { PhoneScreenHeader } from "./PhoneScreenHeader";

/** The view of each chat info block; a new block registers its view here. */
const sectionViews: Record<PhoneChatInfoSectionId, ComponentType<PhoneChatInfoSectionProps>> = {
  summary: PhoneChatSummarySection,
  members: PhoneChatMembersSection,
  note: PhoneGroupNoteSection,
  activity: PhoneChatActivitySection,
  listening: PhoneListeningSection,
};

/**
 * A conversation's chat info page (like a group's 聊天信息 in an IM app),
 * opened from the chat page's header: `sections` (from
 * `phoneChatInfoSections`) as glass cards, top to bottom.
 */
export function PhoneChatInfoPage({ roleId, roleName, app, conversation, sections, active, membersRevision, now, onBack, onOpenMember }: {
  roleId: string;
  roleName: string;
  app: PhoneApp;
  conversation: PhoneConversation;
  sections: readonly PhoneChatInfoSection[];
  /** The page is on top (not covered by a profile opened from it); focus moves to it when it becomes so. */
  active: boolean;
  /** See `PhoneChatInfoSectionProps.membersRevision`. */
  membersRevision: number;
  now: Date;
  onBack: () => void;
  onOpenMember: (senderId: string) => void;
}) {
  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)]">
      <PhoneScreenHeader title="聊天信息" backLabel="返回聊天" onBack={onBack} focusBack={active} />
      <div className="grid min-h-0 content-start gap-2.5 overflow-y-auto p-2.5" data-testid="phone-chat-info-page">
        {sections.map((section) => {
          const View = sectionViews[section.id];
          return (
            <section key={section.id} className="surface-glass grid min-w-0 gap-1.5 rounded-md p-2.5"
              aria-label={section.title} data-testid={`phone-info-${section.id}`}>
              <h4 className="m-0 px-0.5 text-caption font-semibold text-ink-muted">{section.title}</h4>
              <View section={section} roleId={roleId} roleName={roleName} app={app} conversation={conversation}
                onOpenMember={onOpenMember} membersRevision={membersRevision} now={now} />
            </section>
          );
        })}
      </div>
    </div>
  );
}
