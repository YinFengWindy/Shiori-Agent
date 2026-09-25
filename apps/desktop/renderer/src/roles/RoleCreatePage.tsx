import { ArrowCounterClockwise, Plus } from "@phosphor-icons/react";
import { BackIcon, SpinnerIcon } from "../shared/icons";
import { compactButtonSizeClass, cx, ghostButtonSurfaceClass, iconButtonClass, primaryButtonSurfaceClass } from "../shared/styles";
import type { NewRoleFormState } from "../shared/types";
import type { RoleCardImportState } from "../app/roleCardImportState";
import { RoleCreateFields } from "./RoleCreateFields";
import { RoleImportControls } from "./RoleImportControls";
import { selectRoleCreateState } from "./roleCreateSelectors";

type RoleCreatePageProps = {
  bridgeReady: boolean;
  creating: boolean;
  form: NewRoleFormState;
  onBackToList: () => void;
  onCreateRole: () => void;
  onResetForm: () => void;
  onUpdateForm: React.Dispatch<React.SetStateAction<NewRoleFormState>>;
  roleCardImport: RoleCardImportState;
  onPreviewRoleCard: () => void;
  onCancelRoleCardImport: () => void;
};

/** Renders regular role creation using the same identity and import editors as onboarding. */
export function RoleCreatePage({ bridgeReady, creating, form, onBackToList, onCreateRole, onResetForm,
  onUpdateForm, roleCardImport, onPreviewRoleCard, onCancelRoleCardImport }: RoleCreatePageProps) {
  const { formDirty, needsEmotionChoice, previewImagePath } = selectRoleCreateState(form, roleCardImport);
  const canCreate = !creating && bridgeReady && roleCardImport.status !== "previewing" && !needsEmotionChoice;
  return (
    <section className="role-create-page scrollbar-stable relative h-full overflow-y-auto bg-gradient-app bg-fixed" data-testid="role-create-page">
      <div className="mx-auto flex min-h-full w-full max-w-[1120px] flex-col gap-6 px-5 pb-10 pt-6 sm:px-8">
        <div className="flex items-center justify-between gap-3">
          <button className={cx(iconButtonClass, "shadow-soft")} type="button" onClick={onBackToList} disabled={creating} aria-label="返回角色列表" title="返回角色列表"><BackIcon className="h-5 w-5 fill-current" /></button>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <RoleImportControls imported={roleCardImport} form={form} disabled={creating || !bridgeReady}
              onImport={onPreviewRoleCard} onCancel={onCancelRoleCardImport} onUpdateForm={onUpdateForm} />
            <button className={cx(ghostButtonSurfaceClass, compactButtonSizeClass)} type="button" onClick={onResetForm} disabled={creating || !formDirty} aria-label="重置新建角色表单">
              <ArrowCounterClockwise className="h-4 w-4" aria-hidden="true" />
              重置
            </button>
            <button data-testid="create-role-button" className={cx(primaryButtonSurfaceClass, compactButtonSizeClass)} type="button" onClick={onCreateRole}
              disabled={!canCreate} aria-busy={creating}>
              {creating ? <SpinnerIcon className="h-4 w-4 animate-spin stroke-current" /> : <Plus className="h-4 w-4" weight="bold" aria-hidden="true" />}
              {creating ? "正在创建…" : "创建角色"}
            </button>
          </div>
        </div>
        <div className="rounded-xl border border-white/80 bg-white/70 p-6 shadow-soft backdrop-blur-md">
          <RoleCreateFields form={form} disabled={creating || roleCardImport.status === "previewing"} importedAvatar={previewImagePath} onUpdateForm={onUpdateForm} />
        </div>
      </div>
    </section>
  );
}
