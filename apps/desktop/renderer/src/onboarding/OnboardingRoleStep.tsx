import { useRef, useState } from "react";
import { ArrowRight } from "@phosphor-icons/react";
import { useRoleCreationDraft } from "../roles/useRoleCreationDraft";
import { RoleCreateFields } from "../roles/RoleCreateFields";
import { RoleImportControls } from "../roles/RoleImportControls";
import { createRoleFromDraft } from "../roles/roleCreation";
import { selectRoleCreateState } from "../roles/roleCreateSelectors";
import { OnboardingCard } from "./OnboardingCard";
import type { OnboardingReaction } from "./onboardingScript";
import { onboardingActionClass } from "./onboardingStyles";

/** Creates the first role while preserving the draft and preventing duplicate submissions. */
export function OnboardingRoleStep({ onSaved, onBusyChange, onReact }: {
  onSaved: () => Promise<unknown>;
  onBusyChange: (busy: boolean) => void;
  onReact: (reaction: OnboardingReaction) => void;
}) {
  const [error, setError] = useState("");
  const draft = useRoleCreationDraft((message) => {
    setError(message);
    onReact("importFailed");
  });
  const [creating, setCreating] = useState(false);
  const [createdId, setCreatedId] = useState("");
  const pending = useRef(false);
  const { previewImagePath, needsEmotionChoice } = selectRoleCreateState(draft.newRoleForm, draft.roleCardImport);
  const busy = creating || draft.roleCardImport.status === "previewing";
  async function create() {
    if (pending.current || needsEmotionChoice) return;
    pending.current = true;
    setCreating(true);
    onBusyChange(true);
    setError("");
    try {
      // Once persistence succeeds, retry only the refresh, never role creation.
      if (!createdId) {
        const role = await createRoleFromDraft(draft.newRoleFormRef.current, window.miraDesktop.invoke);
        setCreatedId(role.id);
        window.localStorage.setItem("miraDesktop.activeRoleId", role.id);
        draft.clearRoleCardImport();
      }
      await onSaved();
    } catch (error) {
      setError(error instanceof Error ? error.message : String(error));
      onReact("roleCreateFailed");
    } finally {
      pending.current = false;
      setCreating(false);
      onBusyChange(false);
    }
  }
  return (
    <OnboardingCard title="创建角色" error={error}
      headerAction={<RoleImportControls imported={draft.roleCardImport} form={draft.newRoleForm}
        disabled={creating || Boolean(createdId)} onImport={() => void draft.previewRoleCard()} onCancel={() => void draft.cancelRoleCardImport()} onUpdateForm={draft.updateNewRoleForm} />}
      footer={(
        <button type="button" className={onboardingActionClass}
          disabled={busy || needsEmotionChoice || !draft.newRoleForm.name.trim()} onClick={() => void create()}>
          {creating ? "正在创建" : createdId ? "继续" : "创建角色"}<ArrowRight className="h-4 w-4" weight="bold" aria-hidden="true" />
        </button>
      )}>
      <div className="pb-4 pt-2">
        <RoleCreateFields form={draft.newRoleForm} disabled={busy || Boolean(createdId)} importedAvatar={previewImagePath}
          onUpdateForm={(next) => {
            const before = draft.newRoleFormRef.current.avatarSource;
            draft.updateNewRoleForm(next);
            // A newly picked avatar gets a reaction; removing one does not.
            const after = draft.newRoleFormRef.current.avatarSource;
            if (after && after !== before) onReact("avatarPicked");
          }} />
      </div>
    </OnboardingCard>
  );
}
