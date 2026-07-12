import { toFileUrl } from "../shared/format";
import { DeleteIcon, SpinnerIcon } from "../shared/icons";
import { bodyTextClass, cardClass, cx, focusResetClass } from "../shared/styles";
import type { PendingRoleCardAction, RoleRecord } from "../shared/types";

type RoleManagementPageProps = {
  activeRoleId: string;
  bridgeReady: boolean;
  pendingCardAction: PendingRoleCardAction;
  roles: RoleRecord[];
  onOpenRoleDetail: (roleId: string) => void;
  onDeleteRole: (roleId: string) => void;
};

/** Renders the first-level role management screen with the full role list. */
export function RoleManagementPage({
  activeRoleId,
  bridgeReady,
  pendingCardAction,
  roles,
  onOpenRoleDetail,
  onDeleteRole,
}: RoleManagementPageProps) {
  return (
    <section
      className="role-management-page scrollbar-soft scrollbar-soft-accent h-full overflow-y-auto bg-[linear-gradient(180deg,rgba(255,255,255,0.96)_0%,rgba(247,250,253,0.98)_100%)]"
      data-testid="role-management-page"
    >
      <div className="mx-auto flex min-h-full w-full max-w-[1120px] flex-col px-8 pb-10 pt-10">
        {roles.length ? (
          <div className="grid grid-cols-3 gap-5">
            {roles.map((role) => {
              const isActive = role.id === activeRoleId;
              const isPending = pendingCardAction?.roleId === role.id;
              const isDeleting = isPending && pendingCardAction?.action === "delete";
              const isCreating = isPending && pendingCardAction?.action === "create";
              const coverImage = role.chat_background_abs ? toFileUrl(role.chat_background_abs) : "";
              return (
                <button
                  key={role.id}
                  data-testid={`role-management-card-${role.id}`}
                  type="button"
                  disabled={!bridgeReady || isPending}
                  onClick={() => onOpenRoleDetail(role.id)}
                  className={cx(
                    "group relative grid h-[420px] w-full overflow-hidden rounded-[22px] border border-[#D9E0E8] bg-[#EEF1F5] text-left shadow-[0_14px_40px_rgba(31,41,55,0.06)] transition-transform duration-200 hover:-translate-y-0.5 hover:shadow-[0_18px_44px_rgba(31,41,55,0.1)] disabled:cursor-default disabled:opacity-60",
                    focusResetClass,
                    isActive && "shadow-[0_18px_44px_rgba(31,41,55,0.12)]",
                  )}
                  style={coverImage ? { backgroundImage: `url("${coverImage}")`, backgroundSize: "cover", backgroundPosition: "center" } : undefined}
                >
                  {isPending ? (
                    <div className="absolute inset-0 z-[3] bg-[rgba(255,255,255,0.24)] backdrop-blur-[2px]" />
                  ) : null}
                  {isPending ? (
                    <span
                      data-testid={`role-card-spinner-${role.id}`}
                      className="absolute inset-0 z-[4] grid place-items-center"
                      aria-label={isDeleting ? "正在删除角色" : isCreating ? "正在创建角色" : "正在处理中"}
                    >
                      <span className="grid h-16 w-16 place-items-center rounded-full border border-white/30 bg-[rgba(15,23,42,0.62)] text-white shadow-[0_16px_34px_rgba(15,23,42,0.24)]">
                        <SpinnerIcon className="h-7 w-7 animate-spin stroke-current" />
                      </span>
                    </span>
                  ) : null}
                  {coverImage ? null : (
                    <div className="absolute inset-0 bg-[linear-gradient(180deg,#F6F8FB_0%,#E8EEF5_100%)]" />
                  )}
                  <button
                    data-testid={`delete-role-card-${role.id}`}
                    className={cx(
                      "absolute right-4 top-4 z-[2] grid h-9 w-9 place-items-center rounded-full border border-white/24 bg-[rgba(15,23,42,0.62)] text-lg text-white opacity-0 transition duration-200 hover:bg-[rgba(143,43,24,0.88)] group-hover:opacity-100 focus-visible:opacity-100",
                      focusResetClass,
                    )}
                    type="button"
                    disabled={isPending}
                    onClick={(event) => {
                      event.stopPropagation();
                      onDeleteRole(role.id);
                    }}
                    aria-label={`删除角色 ${role.name}`}
                  >
                    <DeleteIcon className="h-[15px] w-[15px] fill-current" />
                  </button>
                  <div className="relative z-[1] flex h-full flex-col justify-between p-5">
                    <div className="flex items-start gap-3">
                      {role.avatar_abs ? (
                        <img
                          className="h-14 w-14 rounded-full border border-[rgba(255,255,255,0.38)] object-cover shadow-[0_4px_16px_rgba(15,23,42,0.18)]"
                          src={toFileUrl(role.avatar_abs)}
                          alt={`${role.name} avatar`}
                        />
                      ) : (
                        <span className="grid h-14 w-14 place-items-center rounded-full border border-[rgba(255,255,255,0.38)] bg-white/75 text-lg font-bold text-[#8a3211] shadow-[0_4px_16px_rgba(15,23,42,0.12)]">
                          {role.name.slice(0, 1).toUpperCase()}
                        </span>
                      )}
                    </div>
                    <div className="min-w-0">
                      <div className="truncate text-[22px] font-semibold leading-none text-[#1f1f1f]">{role.name}</div>
                      <div className={cx(bodyTextClass, "mt-2 line-clamp-2 text-sm leading-6 text-[#5f6873]")}>
                        {role.description || "未填写角色简介"}
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <div className={cx(cardClass, "grid min-h-[280px] place-items-center border-dashed p-8 text-center text-sm text-[#7f7f7f]")}>
            暂无角色，先创建一个角色开始管理。
          </div>
        )}
      </div>
    </section>
  );
}
