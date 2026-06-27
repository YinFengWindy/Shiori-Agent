import { toFileUrl } from "../shared/format";
import { bodyTextClass, cardClass, cx, ghostButtonClass, panelTitleClass, primaryButtonClass } from "../shared/styles";
import type { RoleRecord } from "../shared/types";

type RoleManagementPageProps = {
  activeRoleId: string;
  bridgeReady: boolean;
  roles: RoleRecord[];
  onBackToChat: () => void;
  onCreateRole: () => void;
  onOpenRoleDetail: (roleId: string) => void;
  onOpenRoleSession: (roleId: string) => void;
};

/** Renders the first-level role management screen with the full role list. */
export function RoleManagementPage({
  activeRoleId,
  bridgeReady,
  roles,
  onBackToChat,
  onCreateRole,
  onOpenRoleDetail,
  onOpenRoleSession,
}: RoleManagementPageProps) {
  return (
    <section
      className="role-management-page scrollbar-soft scrollbar-soft-accent h-full overflow-y-auto bg-[linear-gradient(180deg,rgba(255,255,255,0.96)_0%,rgba(247,250,253,0.98)_100%)]"
      data-testid="role-management-page"
    >
      <div className="mx-auto flex min-h-full w-full max-w-[1120px] flex-col px-8 pb-10 pt-10">
        <div className="mb-8 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className={cx(panelTitleClass, "text-[28px] text-[#1f1f1f]")}>角色</h2>
            <p className="mt-2 text-sm text-[#7a7a7a]">从这里查看、进入和维护所有角色。</p>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            <button className={cx("ghost-btn text-sm", ghostButtonClass)} type="button" onClick={onBackToChat}>
              返回聊天
            </button>
            <button
              className={cx("primary-btn text-sm", primaryButtonClass)}
              type="button"
              onClick={onCreateRole}
              disabled={!bridgeReady}
            >
              新建角色
            </button>
          </div>
        </div>
        {roles.length ? (
          <div className="grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-4">
            {roles.map((role) => {
              const isActive = role.id === activeRoleId;
              return (
                <article
                  key={role.id}
                  data-testid={`role-management-card-${role.id}`}
                  className={cx(
                    "grid gap-4 rounded-[22px] border border-[#E7EBF0] bg-white/88 p-5 shadow-[0_14px_40px_rgba(31,41,55,0.06)]",
                    isActive && "border-[rgba(202,93,46,0.28)] shadow-[0_16px_42px_rgba(202,93,46,0.14)]",
                  )}
                >
                  <div className="flex items-start gap-3">
                    {role.avatar_abs ? (
                      <img
                        className="h-14 w-14 rounded-full border border-[rgba(76,48,24,0.12)] object-cover"
                        src={toFileUrl(role.avatar_abs)}
                        alt={`${role.name} avatar`}
                      />
                    ) : (
                      <span className="grid h-14 w-14 place-items-center rounded-full border border-[rgba(76,48,24,0.12)] bg-[#F4F4F4] text-lg font-bold text-[#8a3211]">
                        {role.name.slice(0, 1).toUpperCase()}
                      </span>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-base font-semibold text-[#1f1f1f]">{role.name}</div>
                      <div className={cx(bodyTextClass, "mt-1 line-clamp-2 text-[#858585]")}>
                        {role.description || "未填写角色简介"}
                      </div>
                    </div>
                  </div>
                  <div className="rounded-[16px] bg-[#F7F8FA] px-3.5 py-3 text-[12px] leading-5 text-[#696969]">
                    {role.system_prompt || "未填写系统提示词"}
                  </div>
                  <div className="flex items-center gap-2.5">
                    <button
                      className={cx("ghost-btn text-sm", ghostButtonClass)}
                      type="button"
                      disabled={!bridgeReady}
                      onClick={() => onOpenRoleSession(role.id)}
                    >
                      打开聊天
                    </button>
                    <button
                      className={cx("primary-btn text-sm", primaryButtonClass)}
                      type="button"
                      disabled={!bridgeReady}
                      onClick={() => onOpenRoleDetail(role.id)}
                    >
                      进入详情
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className={cx(cardClass, "grid min-h-[280px] place-items-center border-dashed p-8 text-center text-sm text-[#7f7f7f]")}>
            暂无角色，先创建一个角色再进入管理页。
          </div>
        )}
      </div>
    </section>
  );
}
