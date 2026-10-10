import { ArrowCounterClockwise, Plus } from "@phosphor-icons/react";
import { BackIcon, SpinnerIcon } from "../shared/icons";
import {
  compactButtonSizeClass,
  cx,
  ghostButtonSurfaceClass,
  iconButtonClass,
  primaryButtonSurfaceClass,
} from "@yinfengwindy/shiori-sdk";
import type { NewRoleFormState } from "../shared/types";
import type { RoleCardImportState } from "../app/roleCardImportState";
import { RoleCreateFields } from "./RoleCreateFields";
import { RoleCreateIdentity } from "./RoleCreateIdentity";
import { RoleImportControls } from "./RoleImportControls";
import { selectRoleCreateState } from "./roleCreateSelectors";
import { roleEditorToolbarClass, roleIdentityBackdropClass, roleIdentityCardClass } from "./roleEditorStyles";

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
  const fieldsDisabled = creating || roleCardImport.status === "previewing";
  return (
    <section className="role-create-page scrollbar-stable relative h-full overflow-y-auto bg-gradient-app bg-fixed" data-testid="role-create-page">
      <div className="relative mx-auto flex min-h-full w-full max-w-[1120px] flex-col px-5 pb-10 pt-6 sm:px-8">
        <header className={roleIdentityCardClass} data-testid="role-create-header">
          <div className={roleIdentityBackdropClass} aria-hidden="true" />
          <div className="p-6 sm:p-8">
            <RoleCreateIdentity form={form} disabled={fieldsDisabled} importedAvatar={previewImagePath}
              className="sm:max-w-[62%]" onUpdateForm={onUpdateForm} />
          </div>
        </header>
        <div className={roleEditorToolbarClass} data-testid="role-create-toolbar">
          <button className={cx(iconButtonClass, "self-center")} type="button" onClick={onBackToList} disabled={creating} aria-label="返回角色列表" title="返回角色列表"><BackIcon className="h-5 w-5 fill-current" /></button>
          <div className="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-2 py-2">
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
        <RoleCreateFields form={form} disabled={fieldsDisabled} onUpdateForm={onUpdateForm} />
      </div>
    </section>
  );
}
