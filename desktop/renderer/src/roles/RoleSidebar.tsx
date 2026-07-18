import type React from "react";
import novelAiLogoDark from "../assets/novelai-logo-dark.svg";
import { toFileUrl } from "../shared/format";
import { bodyTextClass, cx } from "../shared/styles";
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
  onOpenRole,
  onOpenImageStudio,
  onOpenPromptTagLibrary,
  onOpenSettings,
  onBeginResize,
}: RoleSidebarProps) {
  const sidebarEntryClass =
    "sidebar-entry grid min-h-[38px] grid-cols-[20px_1fr] items-center gap-2.5 rounded-[10px] border border-transparent bg-transparent px-2 py-0 text-left text-[13px] text-[#3f3f3f] transition-colors hover:border-[#D9E0E8] hover:bg-[#E2E8EF] focus-visible:border-[#D9E0E8] focus-visible:bg-[#E2E8EF] disabled:cursor-default disabled:opacity-[0.45]";
  const roleCardClass =
    "role-card grid min-h-[42px] grid-cols-[32px_minmax(0,1fr)_auto] items-center gap-2.5 rounded-[10px] border border-transparent bg-transparent px-2 py-0 text-left text-[13px] leading-none text-[#404040] transition-colors hover:border-[#D9E0E8] hover:bg-[#E2E8EF] focus-visible:border-[#D9E0E8] focus-visible:bg-[#E2E8EF] disabled:cursor-default disabled:opacity-60";
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
      <div className="sidebar-top grid gap-1.5">
        <button className={sidebarEntryClass} type="button" onClick={onOpenSearch}>
          <span className="sidebar-entry-icon sidebar-entry-search grid h-5 w-5 place-items-center text-[#2c2c2c]" aria-hidden="true">
            <svg viewBox="0 0 1024 1024" className="h-4 w-4 fill-current">
              <path d="M447.957333 149.333333c164.949333 0 298.666667 133.717333 298.666667 298.666667 0 64.96-20.736 125.056-55.936 173.952l177.365333 177.365333a42.666667 42.666667 0 0 1-60.330666 60.330667l-177.365334-177.365333A297.344 297.344 0 0 1 447.957333 746.666667c-164.949333 0-298.666667-133.717333-298.666666-298.666667S283.008 149.333333 447.957333 149.333333z m0 85.333334C330.154667 234.666667 234.624 330.197333 234.624 448s95.530667 213.333333 213.333333 213.333333 213.333333-95.530667 213.333334-213.333333-95.530667-213.333333-213.333334-213.333333z" />
            </svg>
          </span>
          <span>搜索</span>
        </button>
        <button className={sidebarEntryClass} type="button" onClick={onOpenRolesWorkspace}>
          <span className="sidebar-entry-icon sidebar-entry-role grid h-5 w-5 place-items-center text-[#2c2c2c]" aria-hidden="true">
            <svg viewBox="0 0 1024 1024" className="h-4 w-4 fill-current">
              <path d="M356.774 578.668C279.812 528.088 229 440.978 229 342c0-156.297 126.703-283 283-283s283 126.703 283 283c0 98.978-50.812 186.088-127.774 236.668C808.213 638.98 907 778.953 907 942c0 24.3-19.7 44-44 44s-44-19.7-44-44c0-169.551-137.449-307-307-307S205 772.449 205 942c0 24.3-19.7 44-44 44s-44-19.7-44-44c0-163.047 98.787-303.02 239.774-363.332zM512 537c107.696 0 195-87.304 195-195s-87.304-195-195-195-195 87.304-195 195 87.304 195 195 195z" />
            </svg>
          </span>
          <span>角色</span>
        </button>
        <div className="grid grid-cols-[minmax(0,1fr)_38px] gap-1">
          <button className={sidebarEntryClass} type="button" onClick={onOpenImageStudio}>
            <span className="sidebar-entry-icon sidebar-entry-image grid h-5 w-5 place-items-center" aria-hidden="true">
              <img className="h-4 w-4" src={novelAiLogoDark} alt="" />
            </span>
            <span>生图</span>
          </button>
          <button className="grid min-h-[38px] place-items-center rounded-[10px] border border-transparent bg-transparent text-[#3f3f3f] transition-colors hover:border-[#D9E0E8] hover:bg-[#E2E8EF] focus-visible:border-[#D9E0E8] focus-visible:bg-[#E2E8EF]" type="button" aria-label="打开提示词库" title="打开提示词库" onClick={onOpenPromptTagLibrary}>
            <PromptLibraryIcon className="h-4 w-4 fill-current" />
          </button>
        </div>
      </div>
      <div className={cx("role-list scrollbar-soft scrollbar-soft-accent grid min-h-0 content-start gap-1.5 overflow-x-hidden overflow-y-auto pr-0", bodyTextClass)} data-testid="role-list">
        {roles.length ? roles.map((role) => (
          <button
            key={role.id}
            data-testid={`role-card-${role.id}`}
            className={cx(roleCardClass, role.id === activeRoleId && "active bg-white/50 shadow-[0_6px_18px_rgba(15,23,42,0.08)]")}
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
      <div className="sidebar-bottom border-t border-[#E1E5EA] pt-3">
        <button
          data-testid="open-settings-button"
          className={sidebarEntryClass}
          type="button"
          onClick={onOpenSettings}
        >
          <span className="sidebar-entry-icon sidebar-entry-settings grid h-5 w-5 place-items-center text-[#272636]" aria-hidden="true">
            <svg viewBox="0 0 1084 1024" className="h-4 w-4 fill-current">
              <path d="M1072.147851 406.226367c-6.331285-33.456782-26.762037-55.073399-52.047135-55.073399-0.323417 0-0.651455 0.003081-0.830105 0.009241l-4.655674 0c-73.124722 0-132.618162-59.491899-132.618162-132.618162 0-23.731152 11.447443-50.336101 11.546009-50.565574 13.104573-29.498767 3.023185-65.672257-23.427755-84.127081l-1.601687-1.127342-134.400039-74.661726-1.700252-0.745401c-8.753836-3.805547-18.334698-5.735272-28.479231-5.735272-20.789593 0-41.235746 8.344174-54.683758 22.306575-14.741683 15.216028-65.622973 58.649474-104.721083 58.649474-39.450789 0-90.633935-44.286652-105.438762-59.784516-13.518857-14.247316-34.128258-22.753199-55.127302-22.753199-9.945862 0-19.354234 1.861961-27.958682 5.531982l-1.746455 0.74078-139.141957 76.431283-1.643269 1.139662c-26.537186 18.437884-36.675557 54.579032-23.584845 84.062398 0.115506 0.264895 11.579891 26.725075 11.579891 50.634877 0 73.126262-59.491899 132.618162-132.618162 132.618162l-4.581749 0c-0.318797-0.00616-0.636055-0.01078-0.951772-0.01078-25.260456 0-45.672728 21.618157-52.002472 55.0811-0.462025 2.453354-11.313456 60.622322-11.313456 106.117939 0 45.494078 10.85143 103.659965 11.314996 106.119479 6.334365 33.458322 26.758957 55.076479 52.036353 55.076479 0.320337 0 0.651455-0.00616 0.842426-0.012321l4.655674 0c73.126262 0 132.618162 59.491899 132.618162 132.616622 0 23.760413-11.444363 50.333021-11.546009 50.565574-13.093793 29.474125-3.041666 65.646075 23.395414 84.151722l1.569346 1.093459 131.838879 73.726895 1.675611 0.7377c8.750757 3.84251 18.305437 5.790715 28.397607 5.790715 21.082208 0 41.676209-8.706094 55.0888-23.290689 18.724339-20.347588 69.527086-62.362616 107.04815-62.362616 40.625872 0 92.72537 47.100385 107.759669 63.583903 13.441852 14.831008 34.176001 23.689571 55.470741 23.695731l0.00616 0c9.895039 0 19.27877-1.883523 27.893999-5.598205l1.711034-0.73924 136.659342-75.531873 1.617088-1.128882c26.492523-18.456365 36.601633-54.600594 23.538642-84.016195-0.115506-0.267974-11.595291-27.082374-11.595291-50.67646 0-73.124722 59.49344-132.616622 132.618162-132.616622l4.517066-0.00154c0.300316 0.00616 0.599092 0.009241 0.899409 0.009241 25.331299-0.00154 45.785153-21.619697 52.107197-55.054918 0.112426-0.589852 11.325776-59.507301 11.325776-106.14104C1083.464388 466.640776 1072.609877 408.67356 1072.147851 406.226367zM377.486862 945.656142l-115.32764-64.487932c5.082277-13.052211 15.437801-43.51815 15.437801-75.017486 0-109.382917-84.176364-199.816642-192.587488-208.134635-2.647404-15.427021-8.873963-54.967133-8.873963-85.667166 0-30.65691 6.223479-70.232445 8.869343-85.671786 108.415744-8.311832 192.592108-98.745557 192.592108-208.134635 0-31.416171-10.300081-61.797405-15.371577-74.854236l122.721583-67.40331c0.003081 0 0.00462 0.00154 0.007701 0.00154 4.423121 4.518606 22.121764 22.080182 46.558275 39.493911 39.929754 28.46229 77.952885 42.894416 113.014434 42.894416 34.716571 0 72.437845-14.151831 112.115025-42.06431 24.282503-17.07953 41.896442-34.302288 46.308782-38.74543 0.009241-0.00154 0.018481-0.00462 0.026182-0.00616l118.301542 65.726159c-5.077657 13.055291-15.416239 43.499669-15.416239 74.958962 0 109.389077 84.174824 199.822802 192.590568 208.134635 2.645865 15.462442 8.872423 55.107281 8.872423 85.671786 0 30.687711-6.223479 70.241685-8.869343 85.673326C890.042174 606.334084 805.86427 696.767809 805.86427 806.158426c0 31.450053 10.317022 61.851309 15.393138 74.903519l-119.783103 66.198965c-5.168521-5.490399-22.603811-23.363073-46.740005-41.288109-40.701336-30.224145-79.662378-45.549521-115.800446-45.549521-35.79155 0-74.458435 15.038919-114.927219 44.694774C400.22004 922.554885 382.666163 940.255068 377.486862 945.656142zM731.271848 511.646647c0-105.803762-86.081448-191.88059-191.888289-191.88059-105.803762 0-191.88059 86.076827-191.88059 191.88059 0 105.803762 86.076827 191.882129 191.88059 191.882129C645.19194 703.528777 731.271848 617.450409 731.271848 511.646647zM539.383558 395.903184c63.825696 0 115.751164 51.922387 115.751164 115.743463 0 63.825696-51.925468 115.751164-115.751164 115.751164-63.821076 0-115.743463-51.925468-115.743463-115.751164C423.640095 447.824031 475.562482 395.903184 539.383558 395.903184z" />
            </svg>
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
