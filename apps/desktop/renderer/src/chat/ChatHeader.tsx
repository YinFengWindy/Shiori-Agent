import { toFileUrl } from "../shared/format";
import { cx } from "../shared/styles";
import type { RoleRecord } from "../shared/types";

type ChatHeaderProps = {
  activeRole: RoleRecord | null;
  detailRole: RoleRecord | null;
  title: string;
  onOpenRoleDetail: () => void;
};

/** Renders the chat title and role avatar entry point. */
export function ChatHeader({
  activeRole,
  detailRole,
  title,
  onOpenRoleDetail,
}: ChatHeaderProps) {
  const avatarClass =
    "chat-header-avatar grid h-[34px] w-[34px] flex-none place-items-center rounded-full border border-black/10 object-cover";
  return (
    <header className="chat-header relative z-[1] flex min-w-0 items-center gap-3 border-b border-[#E4E4E4] bg-[rgba(255,255,255,0.55)] pl-[23px] pr-6 backdrop-blur-[3px]" data-testid="session-hero">
      {detailRole ? (
        <button
          className="rounded-full transition hover:opacity-90 focus:outline-none"
          type="button"
          aria-label={`查看角色 ${detailRole.name} 详情`}
          data-testid="chat-header-avatar-button"
          onClick={onOpenRoleDetail}
        >
          {detailRole.avatar_abs ? (
            <img
              className={avatarClass}
              src={toFileUrl(detailRole.avatar_abs)}
              alt={`${detailRole.name} avatar`}
            />
          ) : (
            <span className={cx(avatarClass, "chat-header-avatar-fallback bg-[#f6f6f6] text-sm font-bold text-[#333333]")}>
              {detailRole.name.slice(0, 1).toUpperCase()}
            </span>
          )}
        </button>
      ) : activeRole?.avatar_abs ? (
        <img
          className={avatarClass}
          src={toFileUrl(activeRole.avatar_abs)}
          alt={`${activeRole.name} avatar`}
        />
      ) : (
        <span className={cx(avatarClass, "chat-header-avatar-fallback bg-[#f6f6f6] text-sm font-bold text-[#333333]")}>
          {activeRole ? activeRole.name.slice(0, 1).toUpperCase() : "M"}
        </span>
      )}
      <div className="chat-header-title min-w-0 flex-1 truncate text-sm font-semibold text-[#1f1f1f]">{title}</div>
    </header>
  );
}
