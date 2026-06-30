import { bodyTextClass, cx, ghostButtonClass } from "../shared/styles";
import type { RoleFormState, RoleRecord } from "../shared/types";
import { RoleDangerZone, RoleDetailFormPanel, RoleDetailPreviewPanel } from "./RoleDetailPanels";

type RoleDetailPageProps = {
  activeIllustration: string;
  activeRole: RoleRecord | null;
  activeRoleId: string;
  bridgeReady: boolean;
  previewAvatar: string | null;
  previewIllustrations: string[];
  roleForm: RoleFormState;
  roleFormDirty: boolean;
  savingRole: boolean;
  onBackToList: () => void;
  onUpdateRoleForm: React.Dispatch<React.SetStateAction<RoleFormState>>;
  onSetActiveIllustration: (path: string) => void;
  onRememberIllustration: (roleId: string, illustration: string) => void;
  onPickAvatar: () => void;
  onPickIllustrations: () => void;
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
  previewIllustrations,
  roleForm,
  roleFormDirty,
  savingRole,
  onBackToList,
  onUpdateRoleForm,
  onSetActiveIllustration,
  onRememberIllustration,
  onPickAvatar,
  onPickIllustrations,
  onDeleteRole,
  onResetRoleForm,
  onSaveRole,
}: RoleDetailPageProps) {
  return (
    <section
      className="role-detail-page scrollbar-soft scrollbar-soft-accent h-full overflow-y-auto bg-[linear-gradient(180deg,rgba(255,255,255,0.96)_0%,rgba(248,249,252,0.98)_100%)]"
      data-testid="role-detail-page"
    >
      <div className="mx-auto flex min-h-full w-full max-w-[1120px] flex-col px-8 pb-10 pt-10">
        <div className="mb-6 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <button
              className={cx("ghost-btn mb-3 px-3 py-2 text-sm", ghostButtonClass)}
              type="button"
              onClick={onBackToList}
            >
              返回角色列表
            </button>
            <div className="truncate text-[28px] font-semibold text-[#1f1f1f]">
              {activeRole ? activeRole.name : "角色详情"}
            </div>
            <div className={cx(bodyTextClass, "mt-2 text-[#7A7A7A]")}>
              编辑当前角色的基本信息、Prompt 和本地素材。
            </div>
          </div>
        </div>
        <div className="grid min-h-0 gap-5 xl:grid-cols-[minmax(0,1.12fr)_minmax(360px,0.88fr)]">
          <RoleDetailPreviewPanel
            activeRole={activeRole}
            activeRoleId={activeRoleId}
            activeIllustration={activeIllustration}
            bridgeReady={bridgeReady}
            previewAvatar={previewAvatar}
            previewIllustrations={previewIllustrations}
            roleForm={roleForm}
            onPickAvatar={onPickAvatar}
            onPickIllustrations={onPickIllustrations}
            onRememberIllustration={onRememberIllustration}
            onSetActiveIllustration={onSetActiveIllustration}
            onUpdateRoleForm={onUpdateRoleForm}
          />
          <div className="grid content-start gap-5">
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
        </div>
      </div>
    </section>
  );
}
