import { CaretDown } from "@phosphor-icons/react";
import type { RoleProfileDraft } from "../shared/types";
import { RoleEditorSection } from "./RoleEditorSection";
import { RoleTextareaField } from "./RoleTextareaField";

type RoleCardProfileFormProps = {
  profile: RoleProfileDraft;
  onUpdate: (next: RoleProfileDraft) => void;
  /** Keeps optional profile fields folded while creating a role. */
  collapseDetails?: boolean;
};

type CharacterField = keyof NonNullable<RoleProfileDraft["character"]>;

/**
 * Edits structured character fields as two groups: the setting itself, then
 * personality and rules. Every field grows with its text. The knowledge base
 * is managed in its own detail tab.
 */
export function RoleCardProfileForm({
  profile,
  onUpdate,
  collapseDetails = false,
}: RoleCardProfileFormProps) {
  const character = profile.character ?? {};

  function updateCharacter(field: CharacterField, value: string): void {
    onUpdate({ ...profile, character: { ...character, [field]: value } });
  }

  const details = (
    <div className="grid gap-5">
      <div className="grid gap-5 lg:grid-cols-2">
        <RoleTextareaField label="性格" value={character.personality ?? ""} onChange={(value) => updateCharacter("personality", value)} />
        <RoleTextareaField label="执行规则" value={character.behavior_rules ?? ""} onChange={(value) => updateCharacter("behavior_rules", value)} />
      </div>
      <RoleTextareaField label="回复约束" value={character.response_constraints ?? ""} onChange={(value) => updateCharacter("response_constraints", value)} />
    </div>
  );
  const setting = (
    <RoleTextareaField
      ariaLabel="角色设定"
      value={character.profile ?? ""}
      minHeightClass={collapseDetails ? "min-h-32" : "min-h-40"}
      onChange={(value) => updateCharacter("profile", value)}
    />
  );

  if (collapseDetails) {
    return (
      <div className="grid gap-5">
        <RoleEditorSection title="角色设定">{setting}</RoleEditorSection>
        <details className="group border-t border-line-soft pt-3">
          <summary className="flex w-fit cursor-pointer list-none items-center gap-1.5 rounded-md py-1.5 text-body-sm font-medium text-ink-secondary transition-colors hover:text-ink [&::-webkit-details-marker]:hidden">
            更多设定
            <CaretDown className="h-3.5 w-3.5 transition-transform duration-quick group-open:rotate-180" weight="bold" aria-hidden="true" />
          </summary>
          <div className="pt-4">{details}</div>
        </details>
      </div>
    );
  }
  return (
    <>
      <RoleEditorSection title="角色设定">{setting}</RoleEditorSection>
      <RoleEditorSection title="性格与规则">{details}</RoleEditorSection>
    </>
  );
}
