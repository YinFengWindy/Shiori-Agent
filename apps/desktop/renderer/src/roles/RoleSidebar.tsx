import type React from "react";
import novelAiLogoDark from "../assets/novelai-logo-dark.svg";
import { toFileUrl } from "../shared/format";
import { bodyTextClass, cx, sidebarNavItemClass } from "../shared/styles";
import { BookOpenText, GearSix, MagnifyingGlass, Users } from "@phosphor-icons/react";
import { PromptLibraryIcon } from "../shared/icons";
import type { RoleRecord } from "../shared/types";

type RoleSidebarProps = {
  roles: RoleRecord[];
  activeRoleId: string;
  unreadCounts: Record<string, number>;
  bridgeReady: boolean;
  collapsed: boolean;
  animating: boolean;
  width: number;
  onOpenSearch: () => void;
  onOpenRolesWorkspace: () => void;
  onOpenStory: () => void;
  onOpenRole: (roleId: string) => void;
  onOpenImageStudio: () => void;
  onOpenPromptTagLibrary: () => void;
  onOpenSettings: () => void;
  onBeginResize: (event: React.PointerEvent<HTMLDivElement>) => void;
};

/** Renders role navigation, new-role creation, and the sidebar resize handle. */
export function RoleSidebar({
  roles,
  activeRoleId,
  unreadCounts,
  bridgeReady,
  collapsed,
  animating,
  width,
  onOpenSearch,
  onOpenRolesWorkspace,
  onOpenStory,
  onOpenRole,
  onOpenImageStudio,
  onOpenPromptTagLibrary,
  onOpenSettings,
  onBeginResize,
}: RoleSidebarProps) {
  const sidebarEntryClass = cx(
    sidebarNavItemClass,
    "grid grid-cols-[20px_1fr] items-center gap-2.5 px-2 text-left text-[13px] text-[#3a4453] disabled:cursor-default disabled:opacity-[0.45]",
  );
  const sidebarTopEntryClass = cx(sidebarEntryClass, "min-h-[34px]");
  const roleCardClass = cx(
    sidebarNavItemClass,
    "grid min-h-[42px] grid-cols-[32px_minmax(0,1fr)_auto] items-center gap-2.5 px-2 text-left text-[13px] leading-none text-[#3a4453] disabled:cursor-default disabled:opacity-60",
  );
  const roleAvatarClass =
    "role-avatar grid h-8 w-8 place-items-center rounded-full border border-[rgba(76,48,24,0.12)] object-cover";

  return (
    <aside
      className={cx(
        "role-pane relative grid h-full min-h-0 min-w-0 grid-rows-[auto_minmax(0,1fr)_auto] gap-[18px] overflow-hidden bg-transparent py-[18px]",
        animating && "transition-[opacity,transform] duration-[480ms] ease-[cubic-bezier(0.22,1,0.36,1)]",
        collapsed ? "pointer-events-none -translate-x-4 px-0 opacity-0" : "translate-x-0 pl-[18px] pr-[6px] opacity-100",
      )}
      aria-hidden={collapsed}
      style={{ width }}
    >
      <div className="sidebar-top -ml-1 grid gap-1.5">
        <button className={sidebarTopEntryClass} type="button" onClick={onOpenSearch}>
          <span className="sidebar-entry-icon sidebar-entry-search grid h-5 w-5 place-items-center text-[#6b7683]" aria-hidden="true">
            <MagnifyingGlass className="h-[17px] w-[17px]" />
          </span>
          <span>搜索</span>
        </button>
        <button className={sidebarTopEntryClass} type="button" onClick={onOpenRolesWorkspace}>
          <span className="sidebar-entry-icon sidebar-entry-role grid h-5 w-5 place-items-center text-[#6b7683]" aria-hidden="true">
            <Users className="h-[17px] w-[17px]" />
          </span>
          <span>角色</span>
        </button>
        <button data-testid="open-story-button" className={sidebarTopEntryClass} type="button" onClick={onOpenStory}>
          <span className="sidebar-entry-icon grid h-5 w-5 place-items-center text-[#6b7683]" aria-hidden="true">
            <BookOpenText className="h-[17px] w-[17px]" />
          </span>
          <span>故事</span>
        </button>
        <div className="grid grid-cols-[minmax(0,1fr)_34px] gap-1">
          <button className={sidebarTopEntryClass} type="button" onClick={onOpenImageStudio}>
            <span className="sidebar-entry-icon sidebar-entry-image grid h-5 w-5 place-items-center text-[#6b7683]" aria-hidden="true">
              <img className="h-4 w-4" src={novelAiLogoDark} alt="" />
            </span>
            <span>生图</span>
          </button>
          <button className={cx(sidebarNavItemClass, "grid min-h-[34px] place-items-center text-[#3a4453]")} type="button" aria-label="打开提示词库" title="打开提示词库" onClick={onOpenPromptTagLibrary}>
            <PromptLibraryIcon className="h-4 w-4 fill-current" />
          </button>
        </div>
      </div>
      <div className={cx("role-list scrollbar-soft scrollbar-soft-accent grid min-h-0 content-start gap-1.5 overflow-x-hidden overflow-y-auto pr-0", bodyTextClass)} data-testid="role-list">
        {roles.length ? roles.map((role) => (
          <button
            key={role.id}
            data-testid={`role-card-${role.id}`}
            className={cx(roleCardClass, role.id === activeRoleId && "active border-stroke bg-white text-[#2c3440] shadow-[0_6px_18px_rgba(15,23,42,0.08)]")}
            type="button"
            disabled={!bridgeReady}
            onClick={() => onOpenRole(role.id)}
          >
            {role.avatar_abs ? (
              <img
                className={roleAvatarClass}
                src={toFileUrl(role.avatar_abs)}
                alt={`${role.name} avatar`}
              />
            ) : (
              <span className={cx(roleAvatarClass, "bg-white/55 text-sm font-bold text-accent-deep")}>{role.name.slice(0, 1).toUpperCase()}</span>
            )}
            <span className="role-name min-w-0 truncate font-semibold leading-none">{role.name}</span>
            <span className="grid min-h-5 min-w-5 place-items-center">
              {unreadCounts[role.id] ? (
                <span
                  className="h-2.5 w-2.5 rounded-full bg-[#DA4B4B]"
                  aria-label={`${role.name} 有未读主动消息`}
                  title={`${role.name} 有未读主动消息`}
                />
              ) : null}
            </span>
          </button>
        )) : (
          null
        )}
      </div>
      <div className="sidebar-bottom -mb-[18px] -ml-[18px] -mr-[6px] border-t border-stroke">
        <button
          data-testid="open-settings-button"
          className={cx(sidebarEntryClass, "min-h-[46px] w-full rounded-none border-x-0 border-b-0 pl-[22px] pr-[14px]")}
          type="button"
          onClick={onOpenSettings}
        >
          <span className="sidebar-entry-icon sidebar-entry-settings grid h-5 w-5 place-items-center text-[#6b7683]" aria-hidden="true">
            <GearSix className="h-[17px] w-[17px]" />
          </span>
          <span>设置</span>
        </button>
      </div>
      <div
        className={cx(
          "sidebar-resize-handle absolute bottom-0 right-0 top-0 cursor-col-resize bg-transparent",
          collapsed ? "w-0" : "w-2",
        )}
        role="separator"
        aria-label="调整侧边栏宽度"
        aria-orientation="vertical"
        onPointerDown={onBeginResize}
      />
    </aside>
  );
}
