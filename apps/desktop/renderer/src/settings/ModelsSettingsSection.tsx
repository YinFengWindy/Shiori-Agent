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
import { createModelRegistration } from "./modelRegistration";
import { ConfirmDialog } from "../shared/ui/ConfirmDialog";
import { errorMessage, feedback } from "../shared/feedback/feedbackStore";

/** Renders the model registration catalog as list and detail views. */
export function ModelsSettingsSection({
  draft,
  updateDraft,
}: SettingsSectionEditorProps) {
  const [activeRegistrationId, setActiveRegistrationId] = useState<string | null>(null);
  const [pendingRemoval, setPendingRemoval] = useState<ModelRegistrationRemovalPlan | null>(null);
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

  function addRegistration(): void {
    const registration = createModelRegistration();
    updateDraft((current) => ({
      ...current,
      models: {
        registrations: [...current.models.registrations, registration],
      },
    }));
    setActiveRegistrationId(registration.id);
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
      description={pendingRemoval ? describeModelRegistrationRemoval(pendingRemoval) : ""}
      confirmLabel="删除"
      onClose={() => setPendingRemoval(null)}
      onConfirm={confirmRemoval}
    />
  );

  if (activeRegistration) {
    return (
      <>
        <ModelRegistrationDetails
          registration={activeRegistration}
          canDelete
          onBack={() => setActiveRegistrationId(null)}
          onChange={(mutate) => updateRegistration(activeRegistration.id, mutate)}
          onDelete={() => void requestRemoval(activeRegistration)}
        />
        {removalDialog}
      </>
    );
  }

  return (
    <ModelRegistrationList
      registrations={draft.models.registrations}
      onCreate={addRegistration}
      onOpen={setActiveRegistrationId}
    />
  );
}
