import type { RoleCardImportState } from "../app/roleCardImportState";
import type { NewRoleFormState } from "../shared/types";
import { hasUnselectedEmotions } from "./roleCardImportSelectors";

/** Derives reset availability and the decoded image used by the import header. */
export function selectRoleCreateState(form: NewRoleFormState, imported: RoleCardImportState) {
  const character = form.profile?.character;
  const assets = imported.preview?.assets ?? [];
  return {
    formDirty: Boolean(form.avatarSource !== undefined || form.importId || form.name.trim() || form.description.trim() || form.systemPrompt.trim()
      || character?.profile?.trim() || character?.personality?.trim() || character?.behavior_rules?.trim()
      || character?.response_constraints?.trim()),
    needsEmotionChoice: hasUnselectedEmotions(assets, form.emotionSelections ?? {}),
    previewImagePath: assets.find((asset) => asset.kind === "avatar" && asset.preview_abs)?.preview_abs ?? "",
  };
}
