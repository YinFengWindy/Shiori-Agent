import { toFileUrl } from "../shared/format";
import { bodyTextClass, cardClass, cx, ghostButtonClass, inputClass, panelTitleClass } from "../shared/styles";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { RoleDangerZone, RoleDetailFormPanel } from "./RoleDetailPanels";

type RoleDetailPageProps = {
  activeIllustration: string;
  activeRole: RoleRecord | null;
  activeRoleId: string;
  bridgeReady: boolean;
  previewAvatar: string | null;
  featuredImageUrl: string;
  roleForm: RoleFormState;
  roleFormDirty: boolean;
  savingRole: boolean;
  onOpenAssetsPage: () => void;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
  onDeleteRole: () => void;
  onResetRoleForm: () => void;
  onSaveRole: () => void;
};

/** Renders the second-level role detail page and hosts the role editor form. */
export function RoleDetailPage({
  activeIllustration,
  activeRole,
  activeRoleId,
  bridgeReady,
  previewAvatar,
  featuredImageUrl,
  roleForm,
  roleFormDirty,
  savingRole,
  onOpenAssetsPage,
  onUpdateRoleForm,
  onDeleteRole,
  onResetRoleForm,
  onSaveRole,
}: RoleDetailPageProps) {
  return (
    <section
      className="role-detail-page scrollbar-soft scrollbar-soft-accent h-full overflow-y-auto bg-[linear-gradient(180deg,rgba(255,255,255,0.96)_0%,rgba(248,249,252,0.98)_100%)]"
      data-testid="role-detail-page"
    >
      <div className="mx-auto flex min-h-full w-full max-w-[1120px] flex-col gap-5 px-8 pb-10 pt-10">
        <div
          className={cx(cardClass, "relative min-h-[420px] overflow-hidden border-[#D9E0E8] bg-white/88 shadow-[0_18px_48px_rgba(31,41,55,0.08)]")}
          data-testid="role-illustration-hero"
        >
          {featuredImageUrl ? (
            <>
              <div className="absolute inset-0 bg-cover bg-center bg-no-repeat" style={{ backgroundImage: `url("${featuredImageUrl}")` }} />
              <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.06)_0%,rgba(255,255,255,0.1)_34%,rgba(15,23,42,0.58)_100%)]" />
            </>
          ) : (
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,#F8FBFF_0%,#EDF2F8_52%,#E3EAF2_100%)]" />
          )}
        </div>
        <div className={cx(cardClass, "border-[#D9E0E8] bg-white/92 p-5 shadow-[0_18px_48px_rgba(31,41,55,0.08)]")} data-testid="role-detail-info-card">
          <div className="grid gap-5 md:grid-cols-[116px_minmax(0,1fr)]">
            <div className="grid content-start gap-3">
              <div className="relative h-[116px] w-[116px] overflow-hidden rounded-[28px] border border-[#D9E0E8] bg-[radial-gradient(circle_at_top_left,#F8FBFF_0%,#EDF2F8_52%,#E3EAF2_100%)] shadow-[0_14px_32px_rgba(15,23,42,0.08)]" data-testid="role-avatar-card">
                {previewAvatar ? (
                  <img className="h-full w-full object-cover" src={toFileUrl(previewAvatar)} alt={`${activeRole?.name || "角色"} avatar`} />
                ) : (
                  <div className="grid h-full w-full place-items-center text-[34px] font-semibold text-[#8a3211]">
                    {activeRole ? activeRole.name.slice(0, 1).toUpperCase() : "R"}
                  </div>
                )}
              </div>
            </div>
            <div className="grid gap-4">
              <div>
                <div className={panelTitleClass}>{activeRole ? activeRole.name : "角色详情"}</div>
                <div className="mt-2 text-sm text-[#7A8593]">{activeRole?.description || "编辑当前角色的基本信息，并通过素材库管理头像与顶栏立绘。"}</div>
              </div>
              <label className={cx("grid gap-1.5 text-xs text-text", bodyTextClass)}>
                <span>名称</span>
                <input
                  data-testid="edit-role-name"
                  className={inputClass}
                  value={roleForm.name}
                  onChange={(event) => onUpdateRoleForm((current) => ({ ...current, name: event.target.value }))}
                />
              </label>
              <label className={cx("grid gap-1.5 text-xs text-text", bodyTextClass)}>
                <span>简介</span>
                <input
                  data-testid="edit-role-description"
                  className={inputClass}
                  value={roleForm.description}
                  onChange={(event) => onUpdateRoleForm((current) => ({ ...current, description: event.target.value }))}
                />
              </label>
              <div className="grid gap-2 rounded-[18px] border border-[#E4EAF0] bg-[#F8FBFD] px-4 py-3 text-sm text-[#596776]">
                <div className="truncate">当前头像：{activeRole?.avatar || "未设置"}</div>
                <div className="truncate">当前顶栏立绘：{activeRole?.featured_image || "未设置"}</div>
              </div>
              <div className="flex gap-2.5">
                <button
                  data-testid="open-role-assets-button"
                  className={cx("ghost-btn text-sm", ghostButtonClass)}
                  type="button"
                  onClick={onOpenAssetsPage}
                >
                  打开素材库
                </button>
              </div>
            </div>
          </div>
        </div>
        <RoleDetailFormPanel
          bridgeReady={bridgeReady}
          roleForm={roleForm}
          roleFormDirty={roleFormDirty}
          savingRole={savingRole}
          onResetRoleForm={onResetRoleForm}
          onSaveRole={onSaveRole}
          onUpdateRoleForm={onUpdateRoleForm}
        />
        <RoleDangerZone
          bridgeReady={bridgeReady}
          onDeleteRole={onDeleteRole}
        />
      </div>
    </section>
  );
}
