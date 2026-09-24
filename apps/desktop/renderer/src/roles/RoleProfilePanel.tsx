import type { RoleFormState, RoleProfileDraft } from "../shared/types";
import { RoleCardProfileForm } from "./RoleCardProfileForm";
import { RoleModelSection } from "./RoleModelSection";

type RoleProfilePanelProps = {
  roleId: string;
  roleRevision: string;
  bridgeReady: boolean;
  roleForm: RoleFormState;
  onUpdate: (next: React.SetStateAction<RoleFormState>) => void;
  onModelChanged: () => void;
};

/** The 资料 tab: the character's setting, personality and rules, then its models. */
export function RoleProfilePanel({ roleId, roleRevision, bridgeReady, roleForm, onUpdate, onModelChanged }: RoleProfilePanelProps) {
  const profile: RoleProfileDraft = roleForm.profile ?? {
    character: { behavior_rules: roleForm.systemPrompt },
  };

  function updateProfile(nextProfile: RoleProfileDraft): void {
    onUpdate((current) => ({
      ...current,
      profile: nextProfile,
      systemPrompt: nextProfile.character?.behavior_rules ?? current.systemPrompt,
    }));
  }

  return (
    <div className="grid gap-7" data-testid="role-detail-form-panel">
      <RoleCardProfileForm profile={profile} onUpdate={updateProfile} />
      {roleId ? <RoleModelSection roleId={roleId} roleRevision={roleRevision} bridgeReady={bridgeReady} onChanged={onModelChanged} /> : null}
    </div>
  );
}
