import { toFileUrl } from "../shared/format";
import { cx } from "../shared/styles";
import type { RoleRecord } from "../shared/types";
import { ChatTypingSparkles } from "./ChatTypingSparkles";

type ChatHeaderProps = {
  activeRole: RoleRecord | null;
  detailRole: RoleRecord | null;
  title: string;
  /** The role is streaming a reply: shown as a quiet second line, never in place of the name. */
  typing?: boolean;
  onOpenRoleDetail: () => void;
};

const avatarClass =
  "chat-header-avatar grid h-[34px] w-[34px] flex-none place-items-center rounded-full border border-line-soft object-cover";

function HeaderAvatar({ role }: { role: RoleRecord | null }) {
  if (role?.avatar_abs) {
    return <img className={avatarClass} src={toFileUrl(role.avatar_abs)} alt={`${role.name} 的头像`} data-vt-part="avatar" />;
  }
  return (
    <span className={cx(avatarClass, "chat-header-avatar-fallback bg-surface-soft text-sm font-bold text-ink-secondary")} data-vt-part="avatar">
      {role ? role.name.slice(0, 1).toUpperCase() : "M"}
    </span>
  );
}

/**
 * Renders the chat title, the role avatar entry point and the role's typing
 * state. The avatar and name carry `data-vt-part` so a role switch can morph
 * them from the chat list row (see `chatRoleSwitchTransition.ts`).
 */
export function ChatHeader({
  activeRole,
  detailRole,
  title,
  typing = false,
  onOpenRoleDetail,
}: ChatHeaderProps) {
  return (
    <header className="chat-header relative z-[1] flex min-w-0 items-center gap-3 border-b border-white/60 bg-white/55 pl-[23px] pr-6 backdrop-blur-[3px]" data-testid="session-hero" data-chat-header="">
      {detailRole ? (
        <button
          className="rounded-full transition hover:opacity-90 focus:outline-none"
          type="button"
          aria-label={`查看角色 ${detailRole.name} 详情`}
          data-testid="chat-header-avatar-button"
          onClick={onOpenRoleDetail}
        >
          <HeaderAvatar role={detailRole} />
        </button>
      ) : (
        <HeaderAvatar role={activeRole} />
      )}
      <div className="grid min-w-0 flex-1 leading-tight">
        {/* The name hugs its text so the list row's name morphs into it at the right size. */}
        <div className="chat-header-title flex min-w-0">
          <span className="truncate text-sm font-semibold text-ink" data-vt-part="name">{title}</span>
        </div>
        {typing ? (
          <div className="chat-header-typing flex items-center gap-1.5 text-caption text-ink-muted motion-fade-enter" role="status" data-testid="chat-header-typing">
            <ChatTypingSparkles />
            正在输入…
          </div>
        ) : null}
      </div>
    </header>
  );
}
