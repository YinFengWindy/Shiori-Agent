import { useRef, useState } from "react";
import { ArrowRight } from "@phosphor-icons/react";
import type { WorkspaceFeedback } from "../app/appState";
import { useRoleCreationDraft } from "../roles/useRoleCreationDraft";
import { RoleCreateFields } from "../roles/RoleCreateFields";
import { RoleImportControls } from "../roles/RoleImportControls";
import { createRoleFromDraft } from "../roles/roleCreation";
import { selectRoleCreateState } from "../roles/roleCreateSelectors";
import { onboardingActionClass } from "./onboardingStyles";

/** Creates the first role while preserving the draft and preventing duplicate submissions. */
export function OnboardingRoleStep({ onSaved, onBusyChange }: { onSaved: () => Promise<unknown>; onBusyChange: (busy: boolean) => void }) {
  const [feedback, setFeedback] = useState<WorkspaceFeedback | null>(null);
  const draft = useRoleCreationDraft((message) => setFeedback({ tone: "error", message }));
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
    setFeedback(null);
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
      setFeedback({ tone: "error", message: error instanceof Error ? error.message : String(error) });
    } finally {
      pending.current = false;
      setCreating(false);
      onBusyChange(false);
    }
  }
  return (
    <div>
      <div className="mb-5 flex justify-end"><RoleImportControls imported={draft.roleCardImport} form={draft.newRoleForm}
        disabled={creating || Boolean(createdId)} onImport={() => void draft.previewRoleCard()} onCancel={() => void draft.cancelRoleCardImport()} onUpdateForm={draft.updateNewRoleForm} /></div>
      <RoleCreateFields form={draft.newRoleForm} disabled={busy || Boolean(createdId)} importedAvatar={previewImagePath} onUpdateForm={draft.updateNewRoleForm} />
      {feedback ? <p role="alert" className="mt-4 text-sm text-danger-text">{feedback.message}</p> : null}
      <div className="mt-8 flex justify-end"><button type="button" className={onboardingActionClass}
        disabled={busy || needsEmotionChoice || !draft.newRoleForm.name.trim()} onClick={() => void create()}>
        {creating ? "正在创建" : createdId ? "继续" : "创建角色"}<ArrowRight size={18} />
      </button></div>
    </div>
  );
}
