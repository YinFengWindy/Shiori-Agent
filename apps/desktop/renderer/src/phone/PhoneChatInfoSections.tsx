import { CaretRightIcon, UserIcon } from "@phosphor-icons/react";
import { cx, pressableClass } from "@shiori/plugin-sdk";
import { phoneChatSummaryRows, type PhoneChatInfoSection } from "./phoneChatInfo";
import type { PhoneConversation } from "./phoneClient";
import { PhoneInfoEmpty } from "./PhoneInfoEmpty";
import { PhoneLoadError } from "./PhoneLoadError";
import type { PhoneApp } from "./phonePresentation";
import { usePhoneMembers, usePhoneRecentActivity } from "./usePhoneChatMemory";

/** What every chat info block's view receives. */
export type PhoneChatInfoSectionProps = {
  section: PhoneChatInfoSection;
  roleId: string;
  app: PhoneApp;
  conversation: PhoneConversation;
  onOpenMember: (senderId: string) => void;
  /** Changes whenever a member profile opened from this page was saved or deleted. */
  membersRevision: number;
};

const memberButtonClass = cx(
  pressableClass,
  "flex w-full min-w-0 cursor-pointer items-center gap-2 rounded-md px-1.5 py-1.5 text-left hover:bg-surface-hover",
);

/** 群信息: the group (or the other person), the channel, and the role's account carrying it. */
export function PhoneChatSummarySection({ app, conversation }: PhoneChatInfoSectionProps) {
  return (
    <dl className="m-0 grid gap-1">
      {phoneChatSummaryRows(conversation, app).map(({ label, value }) => (
        <div key={label} className="flex min-w-0 items-baseline gap-2 px-0.5">
          <dt className="shrink-0 text-caption text-ink-muted">{label}</dt>
          <dd className="m-0 min-w-0 flex-1 truncate text-right text-body-sm text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** 群成员: profiled members who spoke here; a tap opens the member's profile. */
export function PhoneChatMembersSection(props: PhoneChatInfoSectionProps) {
  // A new revision (a profile was saved or deleted) mounts a fresh list, which reads the members again.
  return <MemberList key={props.membersRevision} {...props} />;
}

function MemberList({ roleId, conversation, onOpenMember }: PhoneChatInfoSectionProps) {
  const { members, error, retry } = usePhoneMembers(roleId, conversation.threadId);
  if (error) return <PhoneLoadError message={error} onRetry={() => void retry()} />;
  if (!members) return null;
  if (!members.length) return <PhoneInfoEmpty label="暂无成员档案" />;
  return (
    <ul className="m-0 grid list-none gap-0.5 p-0" data-testid="phone-info-member-list">
      {members.map((member) => (
        <li key={member.senderId} className="min-w-0">
          <button type="button" className={memberButtonClass} data-testid={`phone-info-member-${member.senderId}`}
            onClick={() => onOpenMember(member.senderId)}>
            <span aria-hidden="true" className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-surface-soft text-ink-muted">
              <UserIcon className="h-3.5 w-3.5" />
            </span>
            <span className="grid min-w-0 flex-1">
              <span className="truncate text-body-sm text-ink">{member.callName}</span>
              {member.brief ? <span className="truncate text-caption text-ink-muted">{member.brief}</span> : null}
            </span>
            <CaretRightIcon className="h-3.5 w-3.5 shrink-0 text-ink-faint" aria-hidden="true" />
          </button>
        </li>
      ))}
    </ul>
  );
}

/** 最近动态: what consolidation last summed up about the conversation; read-only. */
export function PhoneChatActivitySection({ roleId, conversation }: PhoneChatInfoSectionProps) {
  const { activity, error, retry } = usePhoneRecentActivity(roleId, conversation.threadId);
  if (error) return <PhoneLoadError message={error} onRetry={() => void retry()} />;
  if (activity === null) return null;
  if (!activity) return <PhoneInfoEmpty label="暂无" />;
  return <p className="m-0 whitespace-pre-wrap break-words px-0.5 text-body-sm text-ink" data-testid="phone-info-activity-text">{activity}</p>;
}
