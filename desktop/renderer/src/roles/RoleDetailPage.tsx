import { toFileUrl } from "../shared/format";
import { bodyTextClass, cx, ghostButtonClass, inputClass, panelTitleClass } from "../shared/styles";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { RoleDetailFormPanel } from "./RoleDetailPanels";

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
  onBackToList: () => void;
  onOpenAssetsPage: () => void;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
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
  onBackToList,
  onOpenAssetsPage,
  onUpdateRoleForm,
  onResetRoleForm,
  onSaveRole,
}: RoleDetailPageProps) {
  return (
    <section
      className="role-detail-page scrollbar-soft scrollbar-soft-accent relative h-full overflow-y-auto bg-[#EEF2F7]"
      data-testid="role-detail-page"
    >
      {featuredImageUrl ? (
        <div
          className="absolute inset-0 bg-cover bg-center bg-no-repeat"
          style={{ backgroundImage: `url("${featuredImageUrl}")` }}
          data-testid="role-illustration-hero"
        />
      ) : (
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,#F8FBFF_0%,#EDF2F8_52%,#E3EAF2_100%)]" data-testid="role-illustration-hero" />
      )}
      <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(245,247,250,0.22)_0%,rgba(245,247,250,0.38)_22%,rgba(15,23,42,0.46)_100%)]" />
      <div className="relative mx-auto flex w-full max-w-[1120px] flex-col gap-5 px-8 pb-8 pt-8">
        <div className="flex items-start">
          <button
            data-testid="role-detail-back-button"
            className={cx("ghost-btn px-3 py-2 text-sm", ghostButtonClass, "border-white/25 bg-white/14 text-white backdrop-blur-[6px] hover:bg-white/22")}
            type="button"
            onClick={onBackToList}
          >
            返回角色列表
          </button>
        </div>
        <div className="rounded-[28px] border border-white/16 bg-[rgba(255,255,255,0.12)] p-6 shadow-[0_20px_60px_rgba(15,23,42,0.24)] backdrop-blur-[14px]" data-testid="role-detail-info-card">
          <div className="grid gap-5 md:grid-cols-[116px_minmax(0,1fr)]">
            <button
              type="button"
              data-testid="role-avatar-card"
              className="group relative h-[116px] w-[116px] overflow-hidden rounded-[28px] border border-white/24 bg-[rgba(255,255,255,0.18)] text-left shadow-[0_14px_32px_rgba(15,23,42,0.14)] transition hover:scale-[1.01] focus:outline-none focus:ring-2 focus:ring-white/30"
              onClick={onOpenAssetsPage}
            >
              {previewAvatar ? (
                <img className="h-full w-full object-cover" src={toFileUrl(previewAvatar)} alt={`${activeRole?.name || "角色"} avatar`} />
              ) : (
                <div className="grid h-full w-full place-items-center text-[34px] font-semibold text-white">
                  {activeRole ? activeRole.name.slice(0, 1).toUpperCase() : "R"}
                </div>
              )}
              <div className="absolute inset-x-0 bottom-0 bg-[linear-gradient(180deg,rgba(15,23,42,0)_0%,rgba(15,23,42,0.68)_100%)] px-3 py-2 text-[11px] text-white/88">
                打开素材库
              </div>
            </button>
            <div className="grid gap-4">
              <div>
                <div className={cx(panelTitleClass, "text-[34px] leading-none text-white")}>{activeRole ? activeRole.name : "角色详情"}</div>
                <div className="mt-3 text-sm leading-6 text-white/86">{activeRole?.description || "编辑当前角色的基本信息，并通过素材库管理头像与顶栏立绘。"}</div>
              </div>
              <label className={cx("grid gap-1.5 text-xs text-white/85", bodyTextClass)}>
                <span>名称</span>
                <input
                  data-testid="edit-role-name"
                  className={cx(inputClass, "border-white/20 bg-white/16 text-white placeholder:text-white/55")}
                  value={roleForm.name}
                  onChange={(event) => onUpdateRoleForm((current) => ({ ...current, name: event.target.value }))}
                />
              </label>
              <label className={cx("grid gap-1.5 text-xs text-white/85", bodyTextClass)}>
                <span>简介</span>
                <input
                  data-testid="edit-role-description"
                  className={cx(inputClass, "border-white/20 bg-white/16 text-white placeholder:text-white/55")}
                  value={roleForm.description}
                  onChange={(event) => onUpdateRoleForm((current) => ({ ...current, description: event.target.value }))}
                />
              </label>
              <div className="grid gap-2 rounded-[18px] border border-white/16 bg-[rgba(255,255,255,0.12)] px-4 py-3 text-sm text-white/82">
                <div className="truncate">当前头像：{activeRole?.avatar || "未设置"}</div>
                <div className="truncate">当前顶栏立绘：{activeRole?.featured_image || "未设置"}</div>
              </div>
              <label className={cx("grid gap-1.5 text-xs text-white/85", bodyTextClass)} data-testid="role-detail-form-panel">
                <span>系统提示词</span>
                <textarea
                  data-testid="edit-role-prompt"
                  className={cx(inputClass, "min-h-[220px] resize-y border-white/20 bg-white/16 text-white placeholder:text-white/55")}
                  value={roleForm.systemPrompt}
                  onChange={(event) => onUpdateRoleForm((current) => ({ ...current, systemPrompt: event.target.value }))}
                />
              </label>
              <div className="flex gap-2.5">
                <button
                  className={cx("ghost-btn", ghostButtonClass, "border-white/20 bg-white/12 text-white hover:bg-white/18")}
                  type="button"
                  onClick={onResetRoleForm}
                  disabled={!roleFormDirty}
                >
                  重置
                </button>
                <button
                  data-testid="save-role-button"
                  className={cx("ghost-btn border border-transparent bg-white px-[18px] py-3 text-sm text-[#1f1f1f]")}
                  type="button"
                  onClick={onSaveRole}
                  disabled={savingRole || !roleFormDirty || !bridgeReady}
                >
                  {savingRole ? "保存中..." : "保存角色"}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
