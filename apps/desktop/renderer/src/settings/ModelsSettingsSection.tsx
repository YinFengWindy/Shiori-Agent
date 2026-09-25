import { useState } from "react";
import type { ModelRegistrationFormData } from "../../../src/bridge/shared";
import { ModelRegistrationDetails } from "./ModelRegistrationDetails";
import { ModelRegistrationList } from "./ModelRegistrationList";
import {
  describeModelRegistrationRemoval,
  planModelRegistrationRemoval,
  type ModelRegistrationRemovalPlan,
} from "./modelRegistrationRemoval";
import type { SettingsSectionEditorProps } from "./settingsPageTypes";
import { useModelRegistrationDraft } from "./useModelRegistrationDraft";
import { confirmPersonaLines } from "../shared/mascot/mascotLines";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";
import { errorMessage } from "../shared/feedback/feedbackStore";
import { mascotFeedback as feedback } from "../shared/mascot/mascotFeedback";

/** Renders the model registration catalog as list and detail views. */
export function ModelsSettingsSection({
  draft,
  updateDraft,
}: SettingsSectionEditorProps) {
  const [activeRegistrationId, setActiveRegistrationId] = useState<string | null>(null);
  const [pendingRemoval, setPendingRemoval] = useState<ModelRegistrationRemovalPlan | null>(null);
  const newRegistration = useModelRegistrationDraft((registration) => {
    updateDraft((current) => ({
      ...current,
      models: { registrations: [...current.models.registrations, registration] },
    }));
    setActiveRegistrationId(registration.id);
  });
  const activeRegistration = draft.models.registrations.find(
    (registration) => registration.id === activeRegistrationId,
  ) ?? null;

  function updateRegistration(
    id: string,
    mutate: (registration: ModelRegistrationFormData) => ModelRegistrationFormData,
  ): void {
    updateDraft((current) => ({
      ...current,
      models: {
        registrations: current.models.registrations.map((registration) => (
          registration.id === id ? mutate(registration) : registration
        )),
      },
    }));
  }

  async function requestRemoval(registration: ModelRegistrationFormData): Promise<void> {
    try {
      setPendingRemoval(await planModelRegistrationRemoval(registration, draft.pendingRoleModelUpdates));
    } catch (error) {
      feedback.error(`无法删除模型：${errorMessage(error)}`);
    }
  }

  function confirmRemoval(): void {
    if (!pendingRemoval) return;
    const { registration, updates: canRemove } = pendingRemoval;
    setPendingRemoval(null);
    updateDraft((current) => ({
      ...current,
      models: {
        registrations: current.models.registrations.filter((item) => item.id !== registration.id),
      },
      pendingRoleModelUpdates: [
        ...(current.pendingRoleModelUpdates ?? []).filter(
          (item) => !canRemove.some((update) => update.roleId === item.roleId),
        ),
        ...canRemove,
      ],
    }));
    setActiveRegistrationId(null);
  }

  const removalDialog = (
    <ConfirmDialog
      open={pendingRemoval !== null}
      title="删除模型"
      persona={confirmPersonaLines.deleteModel}
      description={pendingRemoval ? describeModelRegistrationRemoval(pendingRemoval) : ""}
      confirmLabel="删除"
      onClose={() => setPendingRemoval(null)}
      onConfirm={confirmRemoval}
    />
  );

  // A new entry is edited here until complete; deleting it or going back just
  // drops it. Both detail branches share one element position, so the edit
  // that completes a draft keeps the same mounted fields (and their focus).
  const detail = newRegistration.draft
    ? {
        registration: newRegistration.draft,
        isDraft: true,
        onBack: newRegistration.discard,
        onChange: newRegistration.update,
        onDelete: newRegistration.discard,
      }
    : activeRegistration
      ? {
          registration: activeRegistration,
          isDraft: false,
          onBack: () => setActiveRegistrationId(null),
          onChange: (mutate: (registration: ModelRegistrationFormData) => ModelRegistrationFormData) => updateRegistration(activeRegistration.id, mutate),
          onDelete: () => void requestRemoval(activeRegistration),
        }
      : null;

  if (detail) {
    return (
      <>
        <ModelRegistrationDetails canDelete {...detail} />
        {removalDialog}
      </>
    );
  }

  return (
    <ModelRegistrationList
      registrations={draft.models.registrations}
      onCreate={newRegistration.start}
      onOpen={setActiveRegistrationId}
    />
  );
}
