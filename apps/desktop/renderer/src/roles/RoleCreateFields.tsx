import type React from "react";
import type { NewRoleFormState, RoleProfileDraft } from "../shared/types";
import { RoleCardProfileForm } from "./RoleCardProfileForm";

/** Edits the same four profile fields for manual creation, imports and the first-run guide. */
export function RoleCreateFields({ form, disabled, onUpdateForm }: {
  form: NewRoleFormState;
  disabled: boolean;
  onUpdateForm: React.Dispatch<React.SetStateAction<NewRoleFormState>>;
}) {
  const profile: RoleProfileDraft = form.profile ?? { character: { behavior_rules: form.systemPrompt } };

  function updateProfile(next: RoleProfileDraft): void {
    onUpdateForm((current) => ({
      ...current,
      profile: next,
      systemPrompt: next.character?.behavior_rules ?? current.systemPrompt,
    }));
  }

  return (
    <fieldset disabled={disabled} className="m-0 min-w-0 border-0 p-0">
      <RoleCardProfileForm profile={profile} onUpdate={updateProfile} />
    </fieldset>
  );
}
