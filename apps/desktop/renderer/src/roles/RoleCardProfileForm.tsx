import { useState } from "react";
import type { RoleProfileDraft } from "../shared/types";
import { CollapsibleField } from "../shared/ui/CollapsibleField";
import { RoleTextareaField } from "./RoleTextareaField";

type RoleCardProfileFormProps = {
  profile: RoleProfileDraft;
  onUpdate: (next: RoleProfileDraft) => void;
};

type CharacterField = keyof NonNullable<RoleProfileDraft["character"]>;

const profileFields = [
  { field: "profile", title: "角色设定" },
  { field: "personality", title: "性格" },
  { field: "behavior_rules", title: "执行规则" },
  { field: "response_constraints", title: "回复约束" },
] satisfies { field: CharacterField; title: string }[];

/** Edits one profile field at a time, retaining draft previews for folded fields. */
export function RoleCardProfileForm({
  profile,
  onUpdate,
}: RoleCardProfileFormProps) {
  const [expandedField, setExpandedField] = useState<CharacterField | null>("profile");
  const character = profile.character ?? {};

  function updateCharacter(field: CharacterField, value: string): void {
    onUpdate({ ...profile, character: { ...character, [field]: value } });
  }

  return (
    <div className="min-w-0">
      {profileFields.map(({ field, title }) => (
        <CollapsibleField key={field} title={title} value={character[field] ?? ""}
          expanded={expandedField === field}
          onToggle={() => setExpandedField((current) => current === field ? null : field)}>
          <RoleTextareaField ariaLabel={title} value={character[field] ?? ""} minHeightClass="min-h-40"
            maxHeight="max(10rem, min(24rem, 50vh))" onChange={(value) => updateCharacter(field, value)} />
        </CollapsibleField>
      ))}
    </div>
  );
}
