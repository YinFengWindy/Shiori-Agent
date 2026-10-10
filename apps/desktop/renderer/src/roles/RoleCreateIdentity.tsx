import type React from "react";
import { cx } from "@yinfengwindy/shiori-sdk";
import type { NewRoleFormState } from "../shared/types";
import { RoleAvatarPicker } from "./RoleAvatarPicker";
import { roleDescriptionInputClass, roleIdentityLayoutClass, roleNameInputClass } from "./roleEditorStyles";

/** Shared avatar, name and intro editor for regular creation and the first-run guide. */
export function RoleCreateIdentity({ form, disabled, importedAvatar, className, onUpdateForm }: {
  form: NewRoleFormState;
  disabled: boolean;
  importedAvatar: string;
  className?: string;
  onUpdateForm: React.Dispatch<React.SetStateAction<NewRoleFormState>>;
}) {
  return (
    <fieldset disabled={disabled} className={cx("m-0 min-w-0 border-0 p-0", roleIdentityLayoutClass, className)}>
      <RoleAvatarPicker source={form.avatarSource ?? importedAvatar} disabled={disabled}
        onChange={(avatarSource) => onUpdateForm((current) => ({ ...current, avatarSource }))} />
      <div className="grid min-w-0 content-center gap-1.5">
        <input data-testid="new-role-name" aria-label="角色名称" className={roleNameInputClass}
          value={form.name} placeholder="未命名角色"
          onChange={(event) => onUpdateForm((current) => ({ ...current, name: event.target.value }))} />
        <input data-testid="new-role-description" aria-label="角色简介" className={roleDescriptionInputClass}
          value={form.description} placeholder="添加一行角色简介"
          onChange={(event) => onUpdateForm((current) => ({ ...current, description: event.target.value }))} />
      </div>
    </fieldset>
  );
}
