import type React from "react";
import type { NewRoleFormState } from "../shared/types";
import { cx } from "../shared/styles";
import { RoleAvatarPicker } from "./RoleAvatarPicker";
import { RoleCardProfileForm } from "./RoleCardProfileForm";
import { roleIdentityInputClass } from "./roleEditorStyles";
import { RoleEditorSection } from "./RoleEditorSection";
import { RoleTextareaField } from "./RoleTextareaField";

/** Shared editable role identity for regular creation and first-run setup; mirrors the role-detail layout. */
export function RoleCreateFields({ form, disabled, importedAvatar, onUpdateForm }: {
  form: NewRoleFormState;
  disabled: boolean;
  importedAvatar: string;
  onUpdateForm: React.Dispatch<React.SetStateAction<NewRoleFormState>>;
}) {
  return (
    <fieldset disabled={disabled} className="m-0 grid min-w-0 gap-7 border-0 p-0">
      <div className="grid items-center gap-6 sm:grid-cols-[auto_minmax(0,1fr)]">
        <RoleAvatarPicker source={form.avatarSource ?? importedAvatar} disabled={disabled}
          onChange={(avatarSource) => onUpdateForm((current) => ({ ...current, avatarSource }))} />
        <div className="grid content-center gap-1.5">
          <input data-testid="new-role-name" aria-label="角色名称"
            className={cx(roleIdentityInputClass, "font-display text-headline text-ink placeholder:text-ink-faint")}
            value={form.name} placeholder="未命名角色"
            onChange={(event) => onUpdateForm((current) => ({ ...current, name: event.target.value }))} />
          <input data-testid="new-role-description" aria-label="角色简介"
            className={cx(roleIdentityInputClass, "text-body text-ink-secondary placeholder:text-ink-faint")}
            value={form.description} placeholder="添加一行角色简介"
            onChange={(event) => onUpdateForm((current) => ({ ...current, description: event.target.value }))} />
        </div>
      </div>
      {form.profile ? <RoleCardProfileForm collapseDetails profile={form.profile} onUpdate={(profile) => onUpdateForm((current) => ({ ...current, profile }))} /> : (
        <RoleEditorSection title="角色设定">
          <RoleTextareaField ariaLabel="角色设定" data-testid="new-role-prompt" minHeightClass="min-h-32"
            value={form.systemPrompt} placeholder="角色的性格、语气与行为"
            onChange={(systemPrompt) => onUpdateForm((current) => ({ ...current, systemPrompt }))} />
        </RoleEditorSection>
      )}
    </fieldset>
  );
}
