import React, { useEffect, useState } from "react";
import { Plus } from "@phosphor-icons/react";
import { emptyStateLines } from "../shared/mascot/mascotLines";
import { MascotEmptyState } from "../shared/mascot/MascotSpeech";
import { useMascotEnabled } from "../shared/mascot/useMascotEnabled";
import { SidebarResizeHandle } from "../shared/SidebarResizeHandle";
import { cx, pressableClass, sidebarContentMotionClass, sidebarNavItemClass } from "../shared/styles";
import type { RoleRecord } from "../shared/types";
import { PetalIcon } from "../shared/ui/icons";
import { RoleAvatar } from "./RoleAvatar";
import { formatChatListTime, previewFromRoleLastMessage, type RoleChatPreview } from "./roleChatPreview";

type RoleSidebarProps = {
  roles: RoleRecord[];
  activeRoleId: string;
  unreadCounts: Record<string, number>;
  /** Live preview of the open conversation; overrides the active role's bridge preview. */
  activeRolePreview?: RoleChatPreview | null;
  bridgeReady: boolean;
  collapsed: boolean;
  animating: boolean;
  width: number;
  onOpenRole: (roleId: string) => void;
  onCreateRole: () => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

/** The relative times in the list only change by the minute. */
const clockTickMs = 60_000;

const createRoleButtonClass = cx(
  pressableClass,
  "inline-flex h-8 items-center gap-1.5 rounded-md border border-white/70 bg-gradient-accent px-3 text-body-sm text-ink shadow-soft hover:brightness-[1.03]",
);

/**
 * Friendly placeholder for a chat list with no roles yet, with the one
 * action that fixes it. With the 看板娘 on, 吟风 says it (her line is an
 * owner-approved exception to 「不写叙述文字」, #362 stage 10).
 */
function RoleSidebarEmptyState({ onCreateRole }: { onCreateRole: () => void }) {
  const createButton = (
    <button className={createRoleButtonClass} type="button" onClick={onCreateRole}>
      <Plus className="h-3.5 w-3.5" weight="bold" aria-hidden="true" />
      新建角色
    </button>
  );
  if (useMascotEnabled()) {
    return (
      <MascotEmptyState line={emptyStateLines.noRoles} layout="stack" className="px-1 pt-6" testId="role-list-empty">
        {createButton}
      </MascotEmptyState>
    );
  }
  return (
    <div className="grid justify-items-center gap-3 px-2 pt-10 text-center" data-testid="role-list-empty">
      <span className="grid h-11 w-11 place-items-center rounded-full bg-accent-softer text-accent">
        <PetalIcon className="h-5 w-5" />
      </span>
      <span className="text-body-sm text-ink-muted">还没有角色</span>
      {createButton}
    </div>
  );
}

const roleCardClass = cx(
  sidebarNavItemClass,
  "grid min-h-[54px] grid-cols-[32px_minmax(0,1fr)] items-center gap-2.5 px-2 py-2 text-left text-[13px] leading-none text-ink-secondary disabled:cursor-default disabled:opacity-60",
);

/** Renders the conversation list sidebar and the sidebar resize handle. */
export function RoleSidebar({
  roles,
  activeRoleId,
  unreadCounts,
  activeRolePreview = null,
  bridgeReady,
  collapsed,
  animating,
  width,
  onOpenRole,
  onCreateRole,
  onBeginResize,
}: RoleSidebarProps) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), clockTickMs);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <aside
      className={cx(
        "role-pane relative grid h-full min-h-0 min-w-0 grid-rows-[minmax(0,1fr)] overflow-hidden bg-transparent py-[18px]",
        animating && sidebarContentMotionClass,
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[18px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <div className="role-list scrollbar-stable grid min-h-0 content-start gap-1.5 overflow-x-hidden overflow-y-auto pr-0" data-testid="role-list">
        {roles.length ? roles.map((role) => {
          const active = role.id === activeRoleId;
          const preview = active && activeRolePreview ? activeRolePreview : previewFromRoleLastMessage(role.last_message);
          const unread = unreadCounts[role.id] ?? 0;
          const time = preview ? formatChatListTime(preview.timestamp, now) : "";
          return (
            <button
              key={role.id}
              data-testid={`role-card-${role.id}`}
              data-chat-role-row={role.id}
              className={cx(roleCardClass, active && "active bg-white text-ink shadow-soft")}
              type="button"
              disabled={!bridgeReady}
              onClick={() => onOpenRole(role.id)}
            >
              <RoleAvatar role={role} />
              <span className="grid min-w-0 gap-1">
                <span className="flex min-w-0 items-baseline gap-2">
                  {/* The name hugs its text (the time is pushed right) so it morphs into the chat header at its own size. */}
                  <span className="role-name min-w-0 truncate font-semibold leading-tight" data-vt-part="name">{role.name}</span>
                  {time ? <span className="ml-auto flex-none text-caption leading-none tabular-nums text-ink-muted">{time}</span> : null}
                </span>
                {preview || unread ? (
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="role-preview min-w-0 flex-1 truncate text-caption leading-tight text-ink-muted" data-testid={`role-preview-${role.id}`}>
                      {preview?.text ?? ""}
                    </span>
                    {unread ? (
                      <span
                        className="grid h-[18px] min-w-[18px] flex-none place-items-center rounded-full bg-danger px-1 text-[11px] font-semibold leading-none tabular-nums text-white"
                        aria-label={`${unread} 条未读主动消息`}
                        data-testid={`role-unread-${role.id}`}
                      >
                        {unread > 99 ? "99+" : unread}
                      </span>
                    ) : null}
                  </span>
                ) : null}
              </span>
            </button>
          );
        }) : bridgeReady ? (
          <RoleSidebarEmptyState onCreateRole={onCreateRole} />
        ) : null}
      </div>
      <SidebarResizeHandle collapsed={collapsed} onBeginResize={onBeginResize} />
    </aside>
  );
}
